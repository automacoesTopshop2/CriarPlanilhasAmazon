# ==============================================================================
# TOPSHOP AMAZON SYSTEM — INTERFACE WEB (FLASK)
# ==============================================================================
# Backend HTTP autenticado, multi-usuário, com auditoria.
#
# Arquitetura:
#   - Auth: Flask-Login + SQLAlchemy + argon2id + CSRF + Limiter + Talisman
#   - Páginas: Jinja (templates/)
#   - Estáticos: static/ (CSS + JS vanilla)
#   - Processamento em background via threading + SSE
# ==============================================================================

import io
import os
import sys
import json

# Raiz do projeto é o pai de site/ — garante CWD e importação de core/ + auth/
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_site_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_root)
for p in (_root, _site_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

import time
import uuid
import queue
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

try:
    from zoneinfo import ZoneInfo
    _BR_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # zoneinfo/tzdata ausente — cai para UTC-3 fixo
    _BR_TZ = timezone(timedelta(hours=-3))

from flask import (
    Flask, render_template, request, jsonify,
    send_file, Response, abort, redirect, url_for
)
from flask_login import LoginManager, current_user, login_required
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix

from core.config import Configuracoes
from core.config_manager import GerenciadorConfig
from core.processadores import ProcessadorSKU, ProcessadorASIN, ProcessadorFULL, ProcessadorLimpeza
from core.carregadores import CarregadorPrecos, CarregadorDescricao, CarregadorDescricaoAPI
from core import amazon_categorias
from core import precificacao_status
from core.utils import Utilitarios
from core import bdamazon_client
from core import amazon_sp_client, amazon_listings

from auth import (
    db, Usuario, auth_bp, admin_bp, config_bp, registrar_evento,
)


# ==============================================================================
# JOB STORE EM MEMÓRIA
# ==============================================================================
class Job:
    __slots__ = ("id", "tipo", "status", "log_queue", "resultado",
                 "criado_em", "mensagem", "progresso", "owner_id")

    def __init__(self, tipo: str, owner_id: Optional[str] = None):
        self.id = uuid.uuid4().hex
        self.tipo = tipo
        self.status = "queued"
        self.log_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.resultado = None
        self.criado_em = datetime.now()
        self.mensagem = ""
        self.progresso = 0.0
        self.owner_id = owner_id


JOBS: Dict[str, Job] = {}
JOBS_LOCK = threading.Lock()


# ---- Persistência em disco para resultados ---------------------------------
# JOBS é per-worker. Quando gunicorn roda com >1 worker, o /download pode
# cair num processo diferente do que processou e o job não está em memória.
# Persistimos o resultado em disco (volume Railway) para o /download poder
# ler de lá; também sobrevive a restart de container.

def _jobs_storage_dir() -> str:
    base = os.getenv("JOBS_STORAGE_DIR")
    if not base:
        data_dir = os.getenv("DATA_DIR") or os.path.join(_root, "_data")
        base = os.path.join(data_dir, "jobs")
    os.makedirs(base, exist_ok=True)
    return base


# --------------------------- Template SKU "pronto" ---------------------------
# Um único template NOGORA (.xlsm) salvo no volume persistente (DATA_DIR), para
# que o usuário não precise reenviá-lo a cada criação por SKU. Global (igual às
# bases de Precificação/Descrição). O sidecar .json guarda o nome original.
def _template_sku_dir() -> str:
    data_dir = os.getenv("DATA_DIR") or os.path.join(_root, "_data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _template_sku_path() -> str:
    return os.path.join(_template_sku_dir(), "template_sku.xlsm")


def _template_sku_meta_path() -> str:
    return os.path.join(_template_sku_dir(), "template_sku.json")


def _salvar_template_sku(dados: bytes, nome_original: str) -> None:
    with open(_template_sku_path(), "wb") as f:
        f.write(dados)
    with open(_template_sku_meta_path(), "w", encoding="utf-8") as f:
        json.dump({"nome_original": nome_original or "template_sku.xlsm"}, f,
                  ensure_ascii=False)


def _ler_template_sku() -> Optional[bytes]:
    caminho = _template_sku_path()
    if not os.path.exists(caminho):
        return None
    with open(caminho, "rb") as f:
        return f.read()


def _remover_template_sku() -> None:
    for p in (_template_sku_path(), _template_sku_meta_path()):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def _template_sku_info() -> dict:
    caminho = _template_sku_path()
    existe = os.path.exists(caminho)
    nome = "template_sku.xlsm"
    atualizado_em = None
    tamanho = None
    if existe:
        try:
            mtime = os.path.getmtime(caminho)
            atualizado_em = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
            tamanho = os.path.getsize(caminho)
        except Exception:
            pass
        try:
            with open(_template_sku_meta_path(), "r", encoding="utf-8") as f:
                nome = (json.load(f) or {}).get("nome_original") or nome
        except Exception:
            pass
    return {
        "existe": existe,
        "arquivo": nome,
        "atualizado_em": atualizado_em,
        "tamanho": tamanho,
    }


def _flag_ligada(valor) -> bool:
    return (valor or "") in ("1", "true", "on", "True")


def _persistir_resultado_em_disco(job_id: str, resultado, owner_id: Optional[str], tipo: str) -> None:
    """Grava arquivo_saida em <jobs_dir>/{id}.xlsm + sidecar {id}.json.
    Chamada após processamento bem-sucedido. Erros não derrubam o job."""
    if not resultado or not resultado.arquivo_saida or not resultado.sucesso:
        return
    try:
        base = _jobs_storage_dir()
        arquivo_path = os.path.join(base, f"{job_id}.xlsm")
        meta_path = os.path.join(base, f"{job_id}.json")
        resultado.arquivo_saida.seek(0)
        with open(arquivo_path, "wb") as f:
            f.write(resultado.arquivo_saida.getvalue())
        meta = {
            "nome_arquivo": resultado.nome_arquivo or "planilha.xlsm",
            "owner_id": owner_id,
            "tipo": tipo,
            "criado_em": datetime.now().isoformat(),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        resultado.arquivo_saida.seek(0)
    except OSError:
        # Volume cheio / sem permissão — segue só com a cópia em memória.
        pass


def _limpar_jobs_antigos(horas: int = 2) -> None:
    agora = datetime.now()
    with JOBS_LOCK:
        for jid, job in list(JOBS.items()):
            if job.status in ("done", "error"):
                idade = (agora - job.criado_em).total_seconds() / 3600
                if idade > horas:
                    JOBS.pop(jid, None)
    # Limpa também os artefatos em disco
    try:
        base = _jobs_storage_dir()
        limite = agora.timestamp() - horas * 3600
        for nome in os.listdir(base):
            if not (nome.endswith(".xlsm") or nome.endswith(".json")):
                continue
            caminho = os.path.join(base, nome)
            try:
                if os.path.getmtime(caminho) < limite:
                    os.remove(caminho)
            except OSError:
                continue
    except OSError:
        pass


# ==============================================================================
# Helpers de inicialização
# ==============================================================================
# Throttle padrão do re-download sob demanda (segundos). As planilhas mudam
# com frequência, mas baixar 6 MB a cada page-load é desperdício — só re-baixa
# se a última sincronização passou desse intervalo.
_THROTTLE_PRECIFICACAO_SEG = int(os.getenv("PRECIFICACAO_THROTTLE_SEG", "600"))

# Evita disparar várias threads de atualização concorrentes (page-loads seguidos).
_SYNC_LOCK = threading.Lock()
_SYNC_EM_ANDAMENTO = False


def _candidatos_sharepoint(gerenciador, cfg):
    """(chave_lógica, share_link, destino_local, rótulo) para cada planilha."""
    return [
        ("precificacao", (gerenciador.get("sharepoint_link_precificacao") or "").strip(),
         cfg.arquivo_precificacao, "Precificação"),
        ("precificacao_full", (gerenciador.get("sharepoint_link_precificacao_full") or "").strip(),
         cfg.arquivo_precificacao_full, "Precificação Full"),
        ("drop_estoque", (gerenciador.get("sharepoint_link_drop_estoque") or "").strip(),
         cfg.arquivo_drop_estoque, "Drop-estoque (NCM)"),
    ]


def _obter_cliente_sharepoint(app: Flask):
    """Retorna um SharePointClient pronto, ou None (com log do motivo)."""
    try:
        from core.sharepoint_client import SharePointClient
    except ImportError as e:
        app.logger.warning("SharePoint indisponível (msal não instalado?): %s", e)
        return None
    cliente = SharePointClient.do_ambiente()
    if cliente is None:
        app.logger.info(
            "SharePoint link(s) configurado(s) mas credenciais ausentes em env "
            "(SHAREPOINT_TENANT_ID/CLIENT_ID/CLIENT_SECRET) — pulando sync."
        )
    return cliente


def _sincronizar_links(app: Flask, gerenciador, cfg, *,
                       throttle_segundos: Optional[int] = None) -> None:
    """Baixa as planilhas configuradas, registrando o estado (origem + sync).

    throttle_segundos=None  -> sempre baixa (usado no startup).
    throttle_segundos=N     -> só baixa o que sincronizou há mais de N segundos.
    """
    from core.sharepoint_client import sincronizar_inteligente

    candidatos = [c for c in _candidatos_sharepoint(gerenciador, cfg) if c[1]]
    if not candidatos:
        return

    # Filtra pelo throttle ANTES de instanciar o cliente (evita rede à toa).
    if throttle_segundos is not None:
        candidatos = [
            c for c in candidatos
            if precificacao_status.precisa_atualizar(c[0], throttle_segundos)
        ]
        if not candidatos:
            return

    cliente = _obter_cliente_sharepoint(app)
    if cliente is None:
        return

    for chave, link, destino, rotulo in candidatos:
        # A Drop-estoque muda de nome (data) todo dia → busca o mais recente
        # da pasta; as demais baixam o arquivo exato do share-link.
        pasta_contem = "drop estoque" if chave == "drop_estoque" else None
        ok, msg, src_lm = sincronizar_inteligente(
            cliente, link, destino, pasta_contem=pasta_contem
        )
        precificacao_status.registrar(
            chave, ok=ok, source_last_modified=src_lm,
            synced_at=precificacao_status.agora_utc_iso(), msg=msg,
        )
        if ok:
            app.logger.info("SharePoint sync OK [%s]: %s", rotulo, msg)
        else:
            app.logger.error(
                "SharePoint sync falhou [%s] (continuando com arquivo local): %s",
                rotulo, msg,
            )


def _sincronizar_sharepoint_startup(app: Flask, gerenciador, cfg) -> None:
    """Sync no startup: baixa tudo que estiver configurado (sem throttle)."""
    _sincronizar_links(app, gerenciador, cfg, throttle_segundos=None)


def _atualizar_precificacao_async(app: Flask) -> None:
    """Dispara, em background, um re-download throttled das planilhas.

    Chamado ao abrir as páginas de criação para manter a base "sempre a mais
    atualizada" sem travar o render. Reentrância protegida: se já houver uma
    atualização em andamento, não dispara outra.
    """
    global _SYNC_EM_ANDAMENTO
    gerenciador = app.config.get("CONFIG_MANAGER")
    cfg = app.config.get("APP_CONFIG")
    if not gerenciador or not cfg:
        return
    if not any(c[1] for c in _candidatos_sharepoint(gerenciador, cfg)):
        return  # nada configurado

    with _SYNC_LOCK:
        if _SYNC_EM_ANDAMENTO:
            return
        _SYNC_EM_ANDAMENTO = True

    def _run():
        global _SYNC_EM_ANDAMENTO
        try:
            _sincronizar_links(app, gerenciador, cfg,
                               throttle_segundos=_THROTTLE_PRECIFICACAO_SEG)
        except Exception as e:
            app.logger.warning("Atualização de precificação em background falhou: %s", e)
        finally:
            with _SYNC_LOCK:
                _SYNC_EM_ANDAMENTO = False

    threading.Thread(target=_run, daemon=True).start()


def _fmt_br(iso: Optional[str]) -> Optional[str]:
    """Converte ISO (UTC) -> 'dd/mm/aaaa HH:MM' no fuso de São Paulo."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_BR_TZ).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return None


def _status_precificacao_br(gerenciador, cfg) -> dict:
    """Resumo do frescor das planilhas, com datas em horário de Brasília.

    Retorna { chave: {label, arquivo, configurado, editado_em, baixado_em,
    ok, msg} } para 'precificacao', 'precificacao_full' e 'drop_estoque'.
    """
    out = {}
    for chave, link, destino, rotulo in _candidatos_sharepoint(gerenciador, cfg):
        reg = precificacao_status.obter(chave) or {}
        out[chave] = {
            "label": rotulo,
            "arquivo": os.path.basename(destino),
            "configurado": bool(link),
            "editado_em": _fmt_br(reg.get("source_last_modified")),
            "baixado_em": _fmt_br(reg.get("synced_at")),
            "ok": reg.get("ok"),
            "msg": reg.get("msg") or "",
        }
    return out


# ==============================================================================
# FACTORY
# ==============================================================================
def create_app(config_overrides: Optional[Dict[str, Any]] = None) -> Flask:
    """
    Application factory. Útil para testes (injeta config diferente)
    e para produção (chamado pelo wsgi/gunicorn).
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    app = Flask(__name__)

    # ---- Config ----
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

    is_prod = os.getenv("ENV", "development") == "production"
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        if is_prod:
            raise RuntimeError(
                "SECRET_KEY é obrigatória em produção. "
                "Gere com: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        secret_key = "dev-secret-change-me"
    app.config["SECRET_KEY"] = secret_key

    # Railway/Heroku emitem DATABASE_URL no formato `postgres://` ou
    # `postgresql://` (driver default psycopg2). Como o requirements usa
    # psycopg3 (`psycopg[binary]`), normalizamos o prefixo para que o
    # SQLAlchemy carregue o driver correto.
    db_url = os.getenv("DATABASE_URL", "sqlite:///auth.db")
    if db_url.startswith("postgres://"):
        db_url = "postgresql+psycopg://" + db_url[len("postgres://"):]
    elif db_url.startswith("postgresql://"):
        db_url = "postgresql+psycopg://" + db_url[len("postgresql://"):]
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    app.config["WTF_CSRF_TIME_LIMIT"] = None  # CSRF token vive enquanto a sessão
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

    # Cookies — Secure só em produção (sem HTTPS em dev local)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = (
        os.getenv("SESSION_COOKIE_SECURE", "1" if is_prod else "0") == "1"
    )
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SECURE"] = app.config["SESSION_COOKIE_SECURE"]
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=7)

    if config_overrides:
        app.config.update(config_overrides)

    # ---- ProxyFix (atrás de Cloudflare/nginx) ----
    if is_prod:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ---- Banco ----
    db.init_app(app)

    # ---- CSRF ----
    csrf = CSRFProtect(app)
    # SSE stream/download e termos antigos não usam CSRF (são GET; o termos *POST*
    # ainda viraá CSRF-protected pelo header X-CSRFToken via fetch)
    app.extensions["csrf"] = csrf

    # ---- Login ----
    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faça login para continuar."
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def carregar_usuario(token: str):
        # Token vem como "<uuid>:<sessao_versao>"; valida ambos
        try:
            uid, versao = token.split(":", 1)
            versao = int(versao)
        except (ValueError, AttributeError):
            return None
        u = db.session.get(Usuario, uid)
        if not u or not u.ativo:
            return None
        if (u.sessao_versao or 1) != versao:
            return None
        return u

    @login_manager.unauthorized_handler
    def _nao_autorizado():
        if request.path.startswith("/api/"):
            return jsonify({"sucesso": False, "mensagem": "Não autenticado."}), 401
        return redirect(url_for("auth.login", next=request.path))

    # ---- Rate Limiter ----
    # Quando REDIS_URL está definido (Railway), usa Redis como storage
    # compartilhado entre workers — proteção contra brute-force funciona
    # corretamente em deploy multi-process. Sem Redis, cai em memory://
    # (válido apenas em single-process; ver `Iniciar Web Producao.bat`).
    redis_url = os.getenv("REDIS_URL", "").strip()
    limiter_storage = redis_url if redis_url else "memory://"
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri=limiter_storage,
        default_limits=[],
    )
    app.extensions["limiter"] = limiter

    # ---- Talisman (CSP + headers) ----
    if not app.config.get("TESTING"):
        csp = {
            "default-src": "'self'",
            "script-src": "'self'",
            "style-src": ["'self'", "https://fonts.googleapis.com"],
            "font-src": ["'self'", "https://fonts.gstatic.com"],
            "img-src": ["'self'", "data:"],
            "connect-src": "'self'",
            "frame-ancestors": "'none'",
        }
        # force_https=False propositalmente: em produção a TLS é terminada
        # no edge (Railway/Cloudflare) e o tráfego interno chega via HTTP.
        # ProxyFix normaliza X-Forwarded-Proto para clients reais, mas o
        # healthcheck interno do Railway não envia esse header — com
        # force_https=True o /healthz retornaria 302 e o deploy ficaria
        # unhealthy. HSTS continua sendo emitido para os clientes externos.
        Talisman(
            app,
            content_security_policy=csp,
            content_security_policy_nonce_in=["script-src"],
            force_https=False,
            strict_transport_security=is_prod,
            session_cookie_secure=app.config["SESSION_COOKIE_SECURE"],
            frame_options="DENY",
            referrer_policy="same-origin",
        )
    else:
        # Talisman injeta `csp_nonce` no contexto Jinja; em testes,
        # provê um fallback vazio para os templates não falharem.
        app.jinja_env.globals.setdefault("csp_nonce", lambda: "")

    # ---- GerenciadorConfig + Configuracoes (compartilhados) ----
    gerenciador = GerenciadorConfig()
    cfg = Configuracoes().aplicar_gerenciador(gerenciador)
    app.config["CONFIG_MANAGER"] = gerenciador
    app.config["APP_CONFIG"] = cfg

    # ---- Estado de frescor das planilhas (ao lado do app_config.json) ----
    precificacao_status.configurar(
        os.path.join(os.path.dirname(os.path.abspath(gerenciador.caminho_arquivo)),
                     "_sync_precificacao.json")
    )

    # ---- Sincronização SharePoint no startup (não-bloqueante em caso de erro) ----
    # Se as credenciais e os caminhos estiverem configurados, baixa a Precificação
    # antes de aceitar requests. Falha → log + segue com arquivo local antigo.
    if not app.config.get("TESTING") and gerenciador.get("sharepoint_sync_no_startup", True):
        _sincronizar_sharepoint_startup(app, gerenciador, cfg)

    # ---- Blueprints ----
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(config_bp)

    # ---- CSRF token disponível em todos os templates ----
    @app.context_processor
    def _inject_csrf():
        return {"csrf_token": generate_csrf}

    # ---- Aplica rate-limit às rotas críticas ----
    # 5 tentativas / 15min por IP em /login
    limiter.limit("5 per 15 minutes", methods=["POST"])(
        app.view_functions["auth.login"]
    )
    # 10 / hora em /registro/<token>
    limiter.limit("10 per hour", methods=["POST"])(
        app.view_functions["auth.registro"]
    )
    # 10 / hora em /reset/<token>
    limiter.limit("10 per hour", methods=["POST"])(
        app.view_functions["auth.reset"]
    )
    # 2FA: limite por IP — fora isso o desafio em si trava após
    # MAX_TENTATIVAS falhas (definido em totp_challenge.py).
    limiter.limit("10 per minute", methods=["POST"])(
        app.view_functions["auth.login_verificar_2fa"]
    )
    limiter.limit("10 per hour", methods=["POST"])(
        app.view_functions["auth.dois_fatores_configurar"]
    )
    limiter.limit("5 per hour", methods=["POST"])(
        app.view_functions["auth.dois_fatores_desabilitar"]
    )
    limiter.limit("5 per hour", methods=["POST"])(
        app.view_functions["auth.dois_fatores_regenerar_backup"]
    )

    # ---- Rotas da aplicação ----
    _registrar_rotas_app(app, cfg)

    return app


# ==============================================================================
# Rotas (movidas para função para encapsular acesso ao app)
# ==============================================================================
def _registrar_rotas_app(app: Flask, config: Configuracoes) -> None:

    def _status_bases():
        cfg_atual = app.config.get("APP_CONFIG", config)
        def _info(caminho: str):
            existe = os.path.exists(caminho)
            atualizado_em = None
            tamanho = None
            if existe:
                try:
                    mtime = os.path.getmtime(caminho)
                    atualizado_em = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
                    tamanho = os.path.getsize(caminho)
                except Exception:
                    pass
            return {
                "arquivo": os.path.basename(caminho),
                "existe": existe,
                "atualizado_em": atualizado_em,
                "tamanho": tamanho,
            }
        gerenciador = app.config.get("CONFIG_MANAGER")
        sharepoint_configurado = bool(
            gerenciador and (gerenciador.get("sharepoint_link_precificacao") or "").strip()
        )
        # Descrição: arquivo local OU API do AgentedeTitulos (quando ativa).
        if getattr(cfg_atual, "usar_api_descricao", False):
            descricao_info = {
                "arquivo": "API AgentedeTitulos (online)",
                "existe": True,
                "atualizado_em": None,
                "tamanho": None,
                "via_api": True,
            }
        else:
            descricao_info = _info(cfg_atual.arquivo_descricao)

        return {
            "precificacao": _info(cfg_atual.arquivo_precificacao),
            "descricao": descricao_info,
            "template_sku": _template_sku_info(),
            "sharepoint_configurado": sharepoint_configurado,
        }

    def _push_log(job, tipo, mensagem, **extras):
        payload = {
            "tipo": tipo,
            "mensagem": mensagem,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            **extras,
        }
        job.log_queue.put(payload)

    # --------------------------- Healthcheck ---------------------------
    @app.route("/healthz")
    def healthz():
        # Endpoint público (sem auth) — usado pelo healthcheck do Railway.
        return ("ok", 200, {"Content-Type": "text/plain; charset=utf-8"})

    # --------------------------- Páginas ---------------------------
    @app.route("/")
    @login_required
    def home():
        return render_template("index.html", bases=_status_bases(), active="dashboard")

    def _ctx_precificacao():
        """Dispara o refresh throttled em background e devolve o status atual
        (datas em horário de Brasília) para o alerta nas páginas de criação."""
        gerenciador = app.config.get("CONFIG_MANAGER")
        cfg_atual = app.config.get("APP_CONFIG", config)
        _atualizar_precificacao_async(app)
        return _status_precificacao_br(gerenciador, cfg_atual)

    @app.route("/sku")
    @login_required
    def page_sku():
        return render_template("sku.html", bases=_status_bases(), active="sku",
                               status_precificacao=_ctx_precificacao(),
                               precif_chave="precificacao")

    @app.route("/asin")
    @login_required
    def page_asin():
        return render_template("asin.html", bases=_status_bases(), active="asin",
                               status_precificacao=_ctx_precificacao(),
                               precif_chave="precificacao")

    @app.route("/full")
    @login_required
    def page_full():
        return render_template("full.html", bases=_status_bases(), active="full",
                               status_precificacao=_ctx_precificacao(),
                               precif_chave="precificacao_full")

    @app.route("/api/precificacao/status")
    @login_required
    def api_precificacao_status():
        """Status de frescor das planilhas (datas em BR). `?refresh=1` dispara
        um re-download throttled em background antes de responder."""
        gerenciador = app.config.get("CONFIG_MANAGER")
        cfg_atual = app.config.get("APP_CONFIG", config)
        if _flag_ligada(request.args.get("refresh")):
            _atualizar_precificacao_async(app)
        return jsonify(_status_precificacao_br(gerenciador, cfg_atual))

    @app.route("/amazon")
    @login_required
    def page_amazon():
        return render_template("amazon.html", bases=_status_bases(), active="amazon",
                               amazon_disponivel=amazon_sp_client.credenciais_ok(),
                               amazon_marketplace=amazon_sp_client.marketplace_id())

    @app.route("/limpeza")
    @login_required
    def page_limpeza():
        cfg_atual = app.config.get("APP_CONFIG", config)
        proc = ProcessadorLimpeza(cfg_atual)
        termos_remover, termos_substituir = proc.carregar_termos()
        return render_template(
            "limpeza.html",
            bases=_status_bases(),
            termos_remover=termos_remover,
            termos_substituir=termos_substituir,
            active="limpeza",
        )

    # --------------------------- API: bases ---------------------------
    @app.route("/api/bases")
    @login_required
    def api_bases():
        return jsonify(_status_bases())

    @app.route("/api/bases/precificacao/upload", methods=["POST"])
    @login_required
    def api_upload_precificacao():
        cfg_atual = app.config.get("APP_CONFIG", config)
        arquivo = request.files.get("arquivo")
        if not arquivo:
            return jsonify({"sucesso": False, "mensagem": "Nenhum arquivo enviado."}), 400
        try:
            with open(cfg_atual.arquivo_precificacao, "wb") as f:
                f.write(arquivo.read())
            return jsonify({"sucesso": True, "mensagem": "Base de Precificação atualizada.", "bases": _status_bases()})
        except Exception as e:
            return jsonify({"sucesso": False, "mensagem": f"Erro ao salvar: {e}"}), 500

    @app.route("/api/bases/descricao/upload", methods=["POST"])
    @login_required
    def api_upload_descricao():
        cfg_atual = app.config.get("APP_CONFIG", config)
        arquivo = request.files.get("arquivo")
        if not arquivo:
            return jsonify({"sucesso": False, "mensagem": "Nenhum arquivo enviado."}), 400
        try:
            with open(cfg_atual.arquivo_descricao, "wb") as f:
                f.write(arquivo.read())
            return jsonify({"sucesso": True, "mensagem": "Base de Descrição atualizada.", "bases": _status_bases()})
        except Exception as e:
            return jsonify({"sucesso": False, "mensagem": f"Erro ao salvar: {e}"}), 500

    # --------------------------- API: template SKU pronto ---------------------------
    @app.route("/api/template/sku/upload", methods=["POST"])
    @login_required
    def api_upload_template_sku():
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            return jsonify({"sucesso": False, "mensagem": "Nenhum arquivo enviado."}), 400
        if not arquivo.filename.lower().endswith(".xlsm"):
            return jsonify({"sucesso": False,
                            "mensagem": "O template precisa ser um arquivo .xlsm."}), 400
        try:
            _salvar_template_sku(arquivo.read(), arquivo.filename)
            return jsonify({"sucesso": True, "mensagem": "Template pronto atualizado.",
                            "bases": _status_bases()})
        except Exception as e:
            return jsonify({"sucesso": False, "mensagem": f"Erro ao salvar: {e}"}), 500

    @app.route("/api/template/sku", methods=["DELETE"])
    @login_required
    def api_delete_template_sku():
        try:
            _remover_template_sku()
            return jsonify({"sucesso": True, "mensagem": "Template pronto removido.",
                            "bases": _status_bases()})
        except Exception as e:
            return jsonify({"sucesso": False, "mensagem": f"Erro ao remover: {e}"}), 500

    # --------------------------- API: termos ---------------------------
    @app.route("/api/termos")
    @login_required
    def api_termos():
        cfg_atual = app.config.get("APP_CONFIG", config)
        proc = ProcessadorLimpeza(cfg_atual)
        remover, substituir = proc.carregar_termos()
        return jsonify({
            "remover": remover,
            "substituir": [{"antigo": k, "novo": v} for k, v in substituir.items()],
        })

    @app.route("/api/termos/remover", methods=["POST"])
    @login_required
    def api_termos_remover_add():
        cfg_atual = app.config.get("APP_CONFIG", config)
        data = request.get_json(silent=True) or {}
        termo = (data.get("termo") or "").strip()
        if not termo:
            return jsonify({"sucesso": False, "mensagem": "Termo vazio."}), 400
        ProcessadorLimpeza(cfg_atual).salvar_termo_remover(termo)
        return jsonify({"sucesso": True})

    @app.route("/api/termos/remover", methods=["DELETE"])
    @login_required
    def api_termos_remover_set():
        cfg_atual = app.config.get("APP_CONFIG", config)
        data = request.get_json(silent=True) or {}
        termos = data.get("termos") or []
        ProcessadorLimpeza(cfg_atual).sobrescrever_termos_remover(termos)
        return jsonify({"sucesso": True})

    @app.route("/api/termos/substituir", methods=["POST"])
    @login_required
    def api_termos_substituir_add():
        cfg_atual = app.config.get("APP_CONFIG", config)
        data = request.get_json(silent=True) or {}
        antigo = (data.get("antigo") or "").strip()
        novo = (data.get("novo") or "").strip()
        if not antigo:
            return jsonify({"sucesso": False, "mensagem": "Termo antigo vazio."}), 400
        ProcessadorLimpeza(cfg_atual).salvar_termo_substituir(antigo, novo)
        return jsonify({"sucesso": True})

    @app.route("/api/termos/substituir", methods=["DELETE"])
    @login_required
    def api_termos_substituir_set():
        cfg_atual = app.config.get("APP_CONFIG", config)
        data = request.get_json(silent=True) or {}
        pares = data.get("pares") or []
        dicio = {p.get("antigo", "").strip(): p.get("novo", "").strip() for p in pares}
        ProcessadorLimpeza(cfg_atual).sobrescrever_termos_substituir(dicio)
        return jsonify({"sucesso": True})

    # --------------------------- API: processamento ---------------------------
    def _executar_em_thread(job, processador, arquivo_entrada, arquivo_template):
        try:
            job.status = "running"
            _push_log(job, "info", "Iniciando processamento...")

            def cb_status(msg):
                job.mensagem = msg
                _push_log(job, "status", msg)

            def cb_progresso(valor):
                job.progresso = valor
                _push_log(job, "progresso", f"{int(valor*100)}%", valor=valor)

            entrada = io.BytesIO(arquivo_entrada)
            template = io.BytesIO(arquivo_template) if arquivo_template else None

            resultado = processador.processar(
                arquivo_entrada=entrada,
                arquivo_template=template,
                callback_status=cb_status,
                callback_progresso=cb_progresso,
            )
            for log in (resultado.logs or []):
                _push_log(job, "log", f"[{log.tipo}] {log.sku}: {log.mensagem}", nivel=log.tipo)
            job.resultado = resultado
            if resultado.sucesso:
                _persistir_resultado_em_disco(job.id, resultado, job.owner_id, job.tipo)
                job.status = "done"
                _push_log(job, "done", resultado.mensagem or "Concluído.",
                          total=resultado.total_processados, erros=resultado.total_erros,
                          avisos=resultado.total_avisos,
                          tempo=round(resultado.tempo_processamento, 2),
                          arquivo=resultado.nome_arquivo)
            else:
                job.status = "error"
                _push_log(job, "error", resultado.mensagem or "Falha no processamento.")
        except Exception as e:
            job.status = "error"
            _push_log(job, "error", f"Exceção não tratada: {e}")
        finally:
            job.log_queue.put({"tipo": "end"})

    def _criar_job(tipo, processador, req):
        arquivo_entrada = req.files.get("arquivo_entrada")
        arquivo_template = req.files.get("arquivo_template")
        if not arquivo_entrada:
            abort(400, description="arquivo_entrada é obrigatório.")
        bytes_entrada = arquivo_entrada.read()

        # Template: upload novo (opcionalmente salvo como "pronto"),
        # ou reaproveita o template pronto salvo no servidor.
        usar_salvo = _flag_ligada(req.form.get("usar_template_salvo"))
        salvar = _flag_ligada(req.form.get("salvar_template"))
        if arquivo_template:
            bytes_template = arquivo_template.read()
            if salvar and bytes_template:
                try:
                    _salvar_template_sku(bytes_template,
                                         arquivo_template.filename or "template_sku.xlsm")
                except Exception as e:
                    app.logger.warning("Falha ao salvar template pronto: %s", e)
        elif usar_salvo:
            bytes_template = _ler_template_sku()
            if not bytes_template:
                abort(400, description=(
                    "Nenhum template pronto salvo. Envie um template .xlsm "
                    "ou marque para salvá-lo."))
        else:
            bytes_template = None
        job = Job(tipo, owner_id=current_user.id if current_user.is_authenticated else None)
        with JOBS_LOCK:
            JOBS[job.id] = job
        _limpar_jobs_antigos()
        threading.Thread(
            target=_executar_em_thread,
            args=(job, processador, bytes_entrada, bytes_template),
            daemon=True,
        ).start()
        return job

    # --------------------------- API: BDAmazon proxy ---------------------------
    @app.route("/api/bdamazon/contas")
    @login_required
    def api_bdamazon_contas():
        """Proxy autenticado para GET /api/v1/contas do BDAmazon.
        Devolve a lista pra UI popular o <select> do formulário manual."""
        if not (os.getenv("BDAMAZON_API_KEY") or "").strip():
            return jsonify({
                "sucesso": False,
                "mensagem": (
                    "BDAMAZON_API_KEY não está configurada no servidor. "
                    "Peça ao admin pra setar a variável no Railway "
                    "(Settings → Variables) com a chave fornecida pelo BDAmazon."
                ),
                "detalhe": "env var BDAMAZON_API_KEY ausente ou vazia",
            }), 503
        try:
            contas = bdamazon_client.listar_contas()
        except bdamazon_client.BDAmazonAuthError as e:
            return jsonify({
                "sucesso": False,
                "mensagem": "BDAmazon recusou a autenticação. Verifique a BDAMAZON_API_KEY.",
                "detalhe": str(e),
            }), 502
        except bdamazon_client.BDAmazonError as e:
            app.logger.error("Falha no BDAmazon /contas: %s", e)
            return jsonify({
                "sucesso": False,
                "mensagem": "Não consegui falar com o BDAmazon.",
                "detalhe": str(e),
            }), 502
        return jsonify({
            "sucesso": True,
            "contas": [
                {
                    "codigo": c.codigo,
                    "nome": c.nome,
                    "marca": c.marca,
                    "tipo_canal": c.tipo_canal,
                    "prefixo_sku": c.prefixo_sku,
                }
                for c in contas
            ],
        })

    # --------------------------- API: criar 1 SKU no BDAmazon -------------------
    @app.route("/api/bdamazon/criar-sku", methods=["POST"])
    @login_required
    def api_bdamazon_criar_sku():
        """Cria 1 SKU no BDAmazon e devolve o sku_market.
        Usado pelo botão 'Solicitar SKU-Market' de cada linha — separa a
        criação no BDAmazon da geração da planilha Amazon."""
        if not (os.getenv("BDAMAZON_API_KEY") or "").strip():
            return jsonify({
                "sucesso": False,
                "mensagem": "BDAMAZON_API_KEY não configurada no servidor.",
                "detalhe": "env var BDAMAZON_API_KEY ausente",
            }), 503
        if not current_user.codigo_externo:
            return jsonify({
                "sucesso": False,
                "mensagem": (
                    "Seu usuário não tem 'codigo_externo' definido. "
                    "Peça ao admin para cadastrar em /admin/usuarios."
                ),
            }), 400
        data = request.get_json(silent=True) or {}
        sku_raiz = (data.get("sku_raiz") or "").strip()
        conta = (data.get("conta_codigo") or "").strip()
        asin = (data.get("asin") or "").strip() or None
        if not sku_raiz or not conta:
            return jsonify({"sucesso": False,
                            "mensagem": "sku_raiz e conta_codigo são obrigatórios."}), 400
        try:
            criado = bdamazon_client.criar_sku(
                conta_codigo=conta,
                sku_raiz=sku_raiz,
                usuario_codigo=current_user.codigo_externo,
                asin=asin,
            )
        except bdamazon_client.BDAmazonAuthError as e:
            return jsonify({"sucesso": False,
                            "mensagem": "BDAmazon recusou a autenticação.",
                            "detalhe": str(e)}), 502
        except bdamazon_client.BDAmazonNotFoundError as e:
            return jsonify({"sucesso": False,
                            "mensagem": "Conta ou usuário desconhecido no BDAmazon.",
                            "detalhe": str(e)}), 404
        except bdamazon_client.BDAmazonRateLimitError as e:
            return jsonify({"sucesso": False,
                            "mensagem": "Rate-limit do BDAmazon (60 req/min). Aguarde alguns segundos.",
                            "detalhe": str(e)}), 429
        except bdamazon_client.BDAmazonError as e:
            app.logger.error("Falha no BDAmazon /skus: %s", e)
            return jsonify({"sucesso": False,
                            "mensagem": "Falha ao criar SKU no BDAmazon.",
                            "detalhe": str(e)}), 502

        # O POST /skus não devolve a classificação de sensibilidade do
        # catálogo; só o GET /skus/{sku_market} traz `status_produto`. Fazemos
        # um GET best-effort logo após criar para já mostrar o badge de risco
        # (LIVRE/SENSIVEL/PROIBIDO) na linha. Falha aqui não invalida a
        # criação — devolvemos status_produto=None e o front mostra "—".
        status_produto = titulo_produto = estoque_produto = None
        try:
            detalhe = bdamazon_client.consultar_sku(criado.sku_market)
            if detalhe is not None:
                status_produto = detalhe.status_produto
                titulo_produto = detalhe.titulo_produto
                estoque_produto = detalhe.estoque_produto
        except bdamazon_client.BDAmazonError as e:
            app.logger.warning(
                "SKU %s criado, mas falha ao consultar status_produto: %s",
                criado.sku_market, e,
            )
        return jsonify({
            "sucesso": True,
            "sku_market": criado.sku_market,
            "sku_raiz": criado.sku_raiz,
            "versao": criado.versao,
            "conta_codigo": criado.conta_codigo,
            "conta_nome": criado.conta_nome,
            "criado_em": criado.criado_em,
            "status_produto": status_produto,
            "titulo_produto": titulo_produto,
            "estoque_produto": estoque_produto,
        })

    # --------------------------- API: criar SKUs em LOTE no BDAmazon ------------
    @app.route("/api/bdamazon/criar-sku-lote", methods=["POST"])
    @login_required
    def api_bdamazon_criar_sku_lote():
        """Cria vários SKUs no BDAmazon numa única chamada (sucesso parcial).

        Usado pelo botão 'Solicitar SKU-Market de todos' — troca N requisições
        unitárias por 1 ao endpoint POST /api/v1/skus/lote. Injeta o
        usuario_codigo do usuário logado em cada item; o navegador nunca envia
        credenciais nem usuario_codigo. Devolve os `resultados` (com `indice`)
        para o front casar cada resultado com a linha da tabela."""
        if not (os.getenv("BDAMAZON_API_KEY") or "").strip():
            return jsonify({
                "sucesso": False,
                "mensagem": "BDAMAZON_API_KEY não configurada no servidor.",
                "detalhe": "env var BDAMAZON_API_KEY ausente",
            }), 503
        if not current_user.codigo_externo:
            return jsonify({
                "sucesso": False,
                "mensagem": (
                    "Seu usuário não tem 'codigo_externo' definido. "
                    "Peça ao admin para cadastrar em /admin/usuarios."
                ),
            }), 400
        data = request.get_json(silent=True) or {}
        itens_in = data.get("itens")
        if not isinstance(itens_in, list) or not itens_in:
            return jsonify({"sucesso": False,
                            "mensagem": "'itens' precisa ser uma lista não-vazia."}), 400

        itens_api = []
        for it in itens_in:
            it = it if isinstance(it, dict) else {}
            itens_api.append({
                "sku_raiz": (it.get("sku_raiz") or "").strip(),
                "conta_codigo": (it.get("conta_codigo") or "").strip(),
                "usuario_codigo": current_user.codigo_externo,
                "asin": ((it.get("asin") or "").strip() or None),
            })

        try:
            resposta = bdamazon_client.criar_skus_lote(itens_api)
        except bdamazon_client.BDAmazonAuthError as e:
            return jsonify({"sucesso": False,
                            "mensagem": "BDAmazon recusou a autenticação.",
                            "detalhe": str(e)}), 502
        except bdamazon_client.BDAmazonNotFoundError as e:
            return jsonify({"sucesso": False,
                            "mensagem": "Conta ou usuário desconhecido no BDAmazon.",
                            "detalhe": str(e)}), 404
        except bdamazon_client.BDAmazonRateLimitError as e:
            return jsonify({"sucesso": False,
                            "mensagem": "Rate-limit do BDAmazon. Aguarde alguns segundos.",
                            "detalhe": str(e)}), 429
        except bdamazon_client.BDAmazonError as e:
            app.logger.error("Falha no BDAmazon /skus/lote: %s", e)
            return jsonify({"sucesso": False,
                            "mensagem": "Falha ao criar SKUs em lote no BDAmazon.",
                            "detalhe": str(e)}), 502

        return jsonify({
            "sucesso": True,
            "total": resposta.get("total", len(itens_api)),
            "criados": resposta.get("criados", 0),
            "falhas": resposta.get("falhas", 0),
            "resultados": resposta.get("resultados", []),
        })

    # --------------------------- API: criar anúncio na Amazon (SP-API) ----------
    @app.route("/api/amazon/criar-oferta", methods=["POST"])
    @login_required
    def api_amazon_criar_oferta():
        """Cria/valida ofertas por ASIN na Amazon via SP-API.

        Body: {itens:[{sku, asin, preco?, quantidade?}], publicar:bool}.
        `publicar=false` (default) roda em VALIDATION_PREVIEW (não publica).
        Preço ausente é puxado da base de Precificação pelo sku (com prefixo da conta).
        """
        if not amazon_sp_client.credenciais_ok():
            return jsonify({
                "sucesso": False,
                "mensagem": ("Credenciais da Amazon SP-API não configuradas no servidor "
                             "(AMAZON_LWA_CLIENT_ID/SECRET, AMAZON_SP_REFRESH_TOKEN, AMAZON_SELLER_ID)."),
            }), 503
        data = request.get_json(silent=True) or {}
        itens = data.get("itens")
        if not isinstance(itens, list) or not itens:
            return jsonify({"sucesso": False, "mensagem": "'itens' precisa ser uma lista não-vazia."}), 400
        publicar = bool(data.get("publicar"))
        modo = None if publicar else "VALIDATION_PREVIEW"

        cfg_atual = app.config.get("APP_CONFIG", config)
        cp = CarregadorPrecos(cfg_atual)
        try:
            cp.carregar()
        except Exception:
            pass  # sem base de preços local; aceita preço vindo no payload

        # Conta fixa TACNAR por enquanto → prefixo p/ formar o sku_market a partir
        # do SKU raiz digitado (ex.: "2812" -> "TACN-2812"). Também acha o preço.
        prefixo_tacnar = next((k for k, v in cfg_atual.mapa_prefixo_conta.items()
                               if str(v).upper() == "TACNAR"), "TACN-")
        resultados = []
        for it in itens:
            it = it if isinstance(it, dict) else {}
            sku = (it.get("sku") or "").strip()
            if not sku:
                raiz = (it.get("sku_raiz") or "").strip()
                if raiz:
                    sku = f"{prefixo_tacnar}{raiz}"
            asin = (it.get("asin") or "").strip()
            preco = it.get("preco")
            if preco in (None, ""):
                preco = cp.obter_preco(sku) if cp.esta_carregado else None
            qtd = int(it.get("quantidade") or 0)
            if not sku or not asin:
                resultados.append({"sku": sku, "asin": asin, "ok": False,
                                   "erros": ["SKU raiz e ASIN são obrigatórios"]})
                continue
            if not preco:
                resultados.append({"sku": sku, "asin": asin, "ok": False,
                                   "erros": ["preço não encontrado (informe na linha ou cadastre na Precificação)"]})
                continue
            try:
                resp = amazon_listings.criar_oferta_por_asin(
                    sku=sku, asin=asin, preco=float(preco), quantidade=qtd, mode=modo)
                r = amazon_listings.resumo_issues(resp)
                resultados.append({"sku": sku, "asin": asin, "preco": str(preco),
                                   "ok": r["total_erros"] == 0, **r})
            except amazon_sp_client.AmazonSPError as e:
                resultados.append({"sku": sku, "asin": asin, "ok": False, "erros": [str(e)[:300]]})
        return jsonify({"sucesso": True,
                        "modo": "publicado" if publicar else "validado",
                        "resultados": resultados})

    @app.route("/api/amazon/criar-produto", methods=["POST"])
    @login_required
    def api_amazon_criar_produto():
        """Cria/valida PRODUTOS NOVOS (do zero) na Amazon via SP-API.

        Body: {categoria, itens:[{sku, ean, marca?, preco?, quantidade?}], publicar:bool}.
        Para cada SKU: puxa título/descrição/bullets/dimensões da base de Descrição
        (API AgentedeTitulos ou planilha), **limpa** os textos (módulo de Limpeza),
        aplica os atributos fixos da categoria e valida/cria. EAN e marca vêm do
        operador. `publicar=false` (default) = VALIDATION_PREVIEW.
        """
        if not amazon_sp_client.credenciais_ok():
            return jsonify({"sucesso": False,
                            "mensagem": "Credenciais da Amazon SP-API não configuradas no servidor."}), 503
        data = request.get_json(silent=True) or {}
        categoria = (data.get("categoria") or "").strip().lower()
        itens = data.get("itens")
        if categoria not in amazon_categorias.PRODUCT_TYPE:
            return jsonify({"sucesso": False,
                            "mensagem": f"categoria inválida: {categoria!r}."}), 400
        if not isinstance(itens, list) or not itens:
            return jsonify({"sucesso": False, "mensagem": "'itens' precisa ser uma lista não-vazia."}), 400
        publicar = bool(data.get("publicar"))
        modo = None if publicar else "VALIDATION_PREVIEW"
        marca_padrao = (data.get("marca") or "").strip()

        cfg_atual = app.config.get("APP_CONFIG", config)
        cp = CarregadorPrecos(cfg_atual)
        try:
            cp.carregar()
        except Exception:
            pass
        cd = (CarregadorDescricaoAPI(cfg_atual) if getattr(cfg_atual, "usar_api_descricao", False)
              else CarregadorDescricao(cfg_atual))
        try:
            cd.carregar()
        except Exception as e:
            return jsonify({"sucesso": False,
                            "mensagem": f"Falha ao carregar base de Descrição: {e}"}), 502
        limp = ProcessadorLimpeza(cfg_atual)
        limp.carregar_termos()

        resultados = []
        for it in itens:
            it = it if isinstance(it, dict) else {}
            sku = (it.get("sku") or "").strip()
            ean = (it.get("ean") or "").strip()
            marca = (it.get("marca") or "").strip() or marca_padrao
            if not sku or not ean:
                resultados.append({"sku": sku, "ok": False, "erros": ["sku e EAN são obrigatórios"]})
                continue
            prod = cd.obter_produto(sku)
            if not prod or not prod.titulo:
                resultados.append({"sku": sku, "ok": False,
                                   "erros": ["produto não encontrado na base de Descrição (título ausente)"]})
                continue
            preco = it.get("preco")
            if preco in (None, ""):
                preco = cp.obter_preco(sku) if cp.esta_carregado else None
            qtd = int(it.get("quantidade") or 0)
            sku_base = Utilitarios.tratar_sku(sku, list(cfg_atual.mapa_prefixo_conta.keys())) or sku
            img = f"{cfg_atual.url_base_imagens}/{sku_base}/{sku_base}_01.jpg"
            # Limpa os textos (mesmo módulo da aba Limpeza) antes de enviar.
            titulo = limp.limpar_texto(prod.titulo)
            descricao = limp.limpar_texto(prod.descricao)
            bullets = [limp.limpar_texto(b) for b in (prod.topicos or []) if b]
            try:
                resp = amazon_listings.criar_produto_por_sku(
                    sku=sku, categoria=categoria, titulo=titulo, descricao=descricao,
                    bullets=bullets, marca=marca, ean=ean,
                    preco=(float(preco) if preco not in (None, "") else None),
                    quantidade=qtd, peso_kg=prod.peso, comprimento_cm=prod.comprimento,
                    largura_cm=prod.largura, altura_cm=prod.altura,
                    imagem_principal_url=img, mode=modo)
                r = amazon_listings.resumo_issues(resp)
                resultados.append({"sku": sku, "ean": ean, "marca": marca,
                                   "ok": r["total_erros"] == 0, **r})
            except amazon_sp_client.AmazonSPError as e:
                resultados.append({"sku": sku, "ok": False, "erros": [str(e)[:300]]})
        return jsonify({"sucesso": True, "categoria": categoria,
                        "modo": "publicado" if publicar else "validado",
                        "resultados": resultados})

    # --------------------------- API: consultar 1 SKU no BDAmazon ---------------
    @app.route("/api/bdamazon/consultar-sku/<sku_market>")
    @login_required
    def api_bdamazon_consultar_sku(sku_market):
        """Proxy para GET /api/v1/skus/{sku_market} do BDAmazon.

        Devolve os dados do SKU + a classificação de sensibilidade do catálogo
        interno (`status_produto`: LIVRE/SENSIVEL/PROIBIDO/INATIVO/None), para a
        UI mostrar o badge de risco ao buscar um SKU-Market já existente.
        """
        if not (os.getenv("BDAMAZON_API_KEY") or "").strip():
            return jsonify({
                "sucesso": False,
                "mensagem": "BDAMAZON_API_KEY não configurada no servidor.",
                "detalhe": "env var BDAMAZON_API_KEY ausente",
            }), 503
        sku_market = (sku_market or "").strip()
        if not sku_market:
            return jsonify({"sucesso": False,
                            "mensagem": "sku_market é obrigatório."}), 400
        try:
            sku = bdamazon_client.consultar_sku(sku_market)
        except bdamazon_client.BDAmazonAuthError as e:
            return jsonify({"sucesso": False,
                            "mensagem": "BDAmazon recusou a autenticação.",
                            "detalhe": str(e)}), 502
        except bdamazon_client.BDAmazonRateLimitError as e:
            return jsonify({"sucesso": False,
                            "mensagem": "Rate-limit do BDAmazon. Aguarde alguns segundos.",
                            "detalhe": str(e)}), 429
        except bdamazon_client.BDAmazonError as e:
            app.logger.error("Falha no BDAmazon GET /skus/%s: %s", sku_market, e)
            return jsonify({"sucesso": False,
                            "mensagem": "Não consegui consultar o SKU no BDAmazon.",
                            "detalhe": str(e)}), 502
        if sku is None:
            return jsonify({"sucesso": False,
                            "mensagem": f"SKU-Market '{sku_market}' não encontrado."}), 404
        return jsonify({
            "sucesso": True,
            "sku_market": sku.sku_market,
            "sku_raiz": sku.sku_raiz,
            "versao": sku.versao,
            "conta_codigo": sku.conta_codigo,
            "conta_nome": sku.conta_nome,
            "asin": sku.asin,
            "ean": sku.ean,
            "titulo": sku.titulo,
            "criado_em": sku.criado_em,
            "criado_por": sku.criado_por,
            "status_produto": sku.status_produto,
            "titulo_produto": sku.titulo_produto,
            "estoque_produto": sku.estoque_produto,
        })

    # --------------------------- API: SKU manual via API BDAmazon ---------------
    def _executar_em_thread_sku_manual(job, processador, entradas, usuario_codigo,
                                       arquivo_template, *, modo_asin=False):
        """Loop: para cada entrada, garante que tenha sku_market (chamando a API
        BDAmazon se ainda não tiver). Depois monta xlsx sintético e delega ao
        ProcessadorSKU ou ProcessadorASIN.

        modo_asin=False -> entrada {sku_raiz, conta_codigo, marca, ean, sku_market?}
                           xlsx sintético tem colunas [SKU, MARCA, EAN]
        modo_asin=True  -> entrada {sku_raiz, conta_codigo, asin, marca, ean, sku_market?}
                           xlsx sintético tem colunas [ASIN, SKU]
        """
        try:
            job.status = "running"
            pendentes = sum(1 for e in entradas if not e.get("sku_market"))
            if pendentes:
                _push_log(job, "info",
                          f"Criando {pendentes} SKU(s) ainda pendentes no BDAmazon...")
            else:
                _push_log(job, "info",
                          f"Todas as {len(entradas)} linha(s) já têm sku_market. "
                          f"Pulando criação no BDAmazon e gerando planilha direto.")

            import openpyxl
            wb_sintetico = openpyxl.Workbook()
            ws = wb_sintetico.active
            if modo_asin:
                ws.title = "ASINs"
                ws.append(["ASIN", "SKU"])
            else:
                ws.title = "SKUs"
                ws.append(["SKU", "MARCA", "EAN"])

            skus_criados = []
            for indice, entrada in enumerate(entradas):
                sku_raiz = (entrada.get("sku_raiz") or "").strip()
                conta = (entrada.get("conta_codigo") or "").strip()
                marca = (entrada.get("marca") or "").strip() or "Genérico"
                ean = (entrada.get("ean") or "").strip()
                asin = (entrada.get("asin") or "").strip()
                sku_market_pre = (entrada.get("sku_market") or "").strip()
                if not sku_raiz or not conta:
                    _push_log(job, "log",
                              f"[ERRO] linha {indice + 1}: sku_raiz e conta são obrigatórios",
                              nivel="Erro")
                    continue
                if modo_asin and not asin:
                    _push_log(job, "log",
                              f"[ERRO] linha {indice + 1}: asin é obrigatório no modo ASIN",
                              nivel="Erro")
                    continue
                if sku_market_pre:
                    sku_market = sku_market_pre
                    versao = entrada.get("versao") or 1
                    _push_log(job, "log",
                              f"[OK] {sku_raiz} -> {sku_market} (já criado anteriormente)",
                              nivel="Info")
                else:
                    try:
                        criado = bdamazon_client.criar_sku(
                            conta_codigo=conta,
                            sku_raiz=sku_raiz,
                            usuario_codigo=usuario_codigo,
                            asin=asin or None,
                        )
                    except bdamazon_client.BDAmazonError as e:
                        _push_log(job, "log",
                                  f"[ERRO] {sku_raiz} ({conta}): {e}",
                                  nivel="Erro")
                        continue
                    sku_market = criado.sku_market
                    versao = criado.versao
                    _push_log(job, "log",
                              f"[OK] {sku_raiz} -> {sku_market} (v{versao})",
                              nivel="Info")
                skus_criados.append({
                    "sku_market": sku_market,
                    "sku_raiz": sku_raiz,
                    "conta_codigo": conta,
                    "versao": versao,
                    "marca": marca,
                    "ean": ean,
                    "asin": asin,
                })
                if modo_asin:
                    ws.append([asin, sku_market])
                else:
                    ws.append([sku_market, marca, ean])

            if not skus_criados:
                job.status = "error"
                _push_log(job, "error",
                          "Nenhuma linha válida — abortando geração da planilha.")
                return

            # Serializa workbook sintético e roda o pipeline existente
            buffer_entrada = io.BytesIO()
            wb_sintetico.save(buffer_entrada)
            buffer_entrada.seek(0)

            _push_log(job, "status",
                      f"{len(skus_criados)} linha(s) prontas. Gerando planilha Amazon...")

            def cb_status(msg):
                job.mensagem = msg
                _push_log(job, "status", msg)

            def cb_progresso(valor):
                job.progresso = valor
                _push_log(job, "progresso",
                          f"{int(valor * 100)}%", valor=valor)

            template = io.BytesIO(arquivo_template) if arquivo_template else None
            resultado = processador.processar(
                arquivo_entrada=buffer_entrada,
                arquivo_template=template,
                callback_status=cb_status,
                callback_progresso=cb_progresso,
            )
            for log_proc in (resultado.logs or []):
                _push_log(job, "log",
                          f"[{log_proc.tipo}] {log_proc.sku}: {log_proc.mensagem}",
                          nivel=log_proc.tipo)
            job.resultado = resultado
            if resultado.sucesso:
                _persistir_resultado_em_disco(job.id, resultado, job.owner_id,
                                              job.tipo)
                job.status = "done"
                _push_log(job, "done", resultado.mensagem or "Concluído.",
                          total=resultado.total_processados,
                          erros=resultado.total_erros,
                          avisos=resultado.total_avisos,
                          tempo=round(resultado.tempo_processamento, 2),
                          arquivo=resultado.nome_arquivo,
                          skus_market=[s["sku_market"] for s in skus_criados])
            else:
                job.status = "error"
                _push_log(job, "error",
                          resultado.mensagem or "Falha no processamento.")
        except Exception as e:
            job.status = "error"
            _push_log(job, "error", f"Exceção não tratada: {e}")
        finally:
            job.log_queue.put({"tipo": "end"})

    def _processar_manual_compartilhado(processador, modo_asin: bool,
                                        tipo_job: Optional[str] = None):
        """Lógica comum a /api/processar/sku-manual, /asin-manual e /full-manual.
        Devolve (status, json_response).

        tipo_job: rótulo do Job (default: 'asin-manual' se modo_asin senão
        'sku-manual'). O FULL passa 'full' para categorizar os resultados."""
        if not current_user.codigo_externo:
            return 400, {
                "sucesso": False,
                "mensagem": (
                    "Seu usuário não tem 'codigo_externo' definido. "
                    "Peça ao admin pra cadastrar o seu código do BDAmazon "
                    "em /admin/usuarios."
                ),
            }
        entradas_raw = request.form.get("entradas")
        if not entradas_raw:
            return 400, {"sucesso": False, "mensagem": "Campo 'entradas' ausente."}
        try:
            entradas = json.loads(entradas_raw)
        except ValueError:
            return 400, {"sucesso": False,
                         "mensagem": "Campo 'entradas' não é JSON válido."}
        if not isinstance(entradas, list) or not entradas:
            return 400, {"sucesso": False,
                         "mensagem": "'entradas' precisa ser lista não-vazia."}
        arquivo_template = request.files.get("arquivo_template")
        usar_salvo = _flag_ligada(request.form.get("usar_template_salvo"))
        salvar = _flag_ligada(request.form.get("salvar_template"))
        if arquivo_template:
            bytes_template = arquivo_template.read()
            if salvar and bytes_template:
                try:
                    _salvar_template_sku(bytes_template,
                                         arquivo_template.filename or "template_sku.xlsm")
                except Exception as e:
                    app.logger.warning("Falha ao salvar template pronto: %s", e)
        elif usar_salvo:
            bytes_template = _ler_template_sku()
            if not bytes_template:
                return 400, {"sucesso": False, "mensagem": (
                    "Nenhum template pronto salvo. Envie um template .xlsm "
                    "ou marque para salvá-lo.")}
        else:
            return 400, {"sucesso": False,
                         "mensagem": "arquivo_template é obrigatório (ou use o template pronto)."}

        job = Job(tipo_job or ("asin-manual" if modo_asin else "sku-manual"),
                  owner_id=current_user.id)
        with JOBS_LOCK:
            JOBS[job.id] = job
        _limpar_jobs_antigos()
        threading.Thread(
            target=_executar_em_thread_sku_manual,
            args=(job, processador, entradas,
                  current_user.codigo_externo, bytes_template),
            kwargs={"modo_asin": modo_asin},
            daemon=True,
        ).start()
        return 200, {"job_id": job.id}

    @app.route("/api/processar/asin-manual", methods=["POST"])
    @login_required
    def api_processar_asin_manual():
        cfg_atual = app.config.get("APP_CONFIG", config)
        status, body = _processar_manual_compartilhado(
            ProcessadorASIN(cfg_atual), modo_asin=True
        )
        return jsonify(body), status

    @app.route("/api/processar/full-manual", methods=["POST"])
    @login_required
    def api_processar_full_manual():
        """Modalidade FULL (CONTA-CLA + Logística da Amazon). Mesma entrada do
        ASIN manual (sku_raiz + conta_codigo CLA + asin → resolve sku_market no
        BDAmazon), mas gera com preço da Precificação Full (aba CLA), NCM da
        Drop-estoque e colunas fixas próprias do FULL."""
        cfg_atual = app.config.get("APP_CONFIG", config)
        status, body = _processar_manual_compartilhado(
            ProcessadorFULL(cfg_atual), modo_asin=True, tipo_job="full"
        )
        return jsonify(body), status

    @app.route("/api/processar/sku-manual", methods=["POST"])
    @login_required
    def api_processar_sku_manual():
        """Recebe entradas digitadas (lista JSON) + template .xlsm.
        Para cada entrada: se já vier com sku_market resolvido, usa direto;
        senão chama POST /api/v1/skus do BDAmazon. Depois gera planilha Amazon
        via ProcessadorSKU."""
        cfg_atual = app.config.get("APP_CONFIG", config)
        status, body = _processar_manual_compartilhado(
            ProcessadorSKU(cfg_atual), modo_asin=False
        )
        return jsonify(body), status

    @app.route("/api/processar/sku", methods=["POST"])
    @login_required
    def api_processar_sku():
        cfg_atual = app.config.get("APP_CONFIG", config)
        job = _criar_job("sku", ProcessadorSKU(cfg_atual), request)
        return jsonify({"job_id": job.id})

    @app.route("/api/processar/asin", methods=["POST"])
    @login_required
    def api_processar_asin():
        cfg_atual = app.config.get("APP_CONFIG", config)
        job = _criar_job("asin", ProcessadorASIN(cfg_atual), request)
        return jsonify({"job_id": job.id})

    @app.route("/api/processar/limpeza", methods=["POST"])
    @login_required
    def api_processar_limpeza():
        cfg_atual = app.config.get("APP_CONFIG", config)
        job = _criar_job("limpeza", ProcessadorLimpeza(cfg_atual), request)
        return jsonify({"job_id": job.id})

    @app.route("/api/jobs/<job_id>/stream")
    @login_required
    def api_job_stream(job_id):
        job = JOBS.get(job_id)
        if not job:
            abort(404)
        # Só dono ou admin acessa o stream
        if job.owner_id and current_user.id != job.owner_id and not current_user.is_admin:
            abort(403)

        def gerar():
            yield ":connected\n\n"
            while True:
                try:
                    evento = job.log_queue.get(timeout=30)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                if evento.get("tipo") == "end":
                    break

        return Response(gerar(), headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        })

    @app.route("/api/jobs/<job_id>/download")
    @login_required
    def api_job_download(job_id):
        # Disco é a fonte canônica. Servir sempre dele evita dois bugs
        # comuns em deploys multi-worker:
        #   1) JOBS é per-worker — request pode cair num processo que não
        #      processou o job → 404 → navegador salva HTML como .htm.
        #   2) BytesIO em send_file pode ser fechado pelo wrap do werkzeug
        #      após a 1ª resposta — clicar "baixar" de novo gera 500/HTML.
        # Fallback de memória só serve se o persist em disco falhou.
        base = _jobs_storage_dir()
        arquivo_path = os.path.join(base, f"{job_id}.xlsm")
        meta_path = os.path.join(base, f"{job_id}.json")

        if os.path.exists(arquivo_path) and os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, json.JSONDecodeError):
                abort(500)
            owner_id = meta.get("owner_id")
            if owner_id and current_user.id != owner_id and not current_user.is_admin:
                abort(403)
            return send_file(
                arquivo_path,
                as_attachment=True,
                download_name=meta.get("nome_arquivo") or "planilha.xlsm",
                mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
            )

        # Disco indisponível: tenta a cópia em memória (cria buffer novo
        # para evitar issues de stream fechado em downloads repetidos).
        job = JOBS.get(job_id)
        if not job or not job.resultado or not job.resultado.arquivo_saida:
            abort(404)
        if job.owner_id and current_user.id != job.owner_id and not current_user.is_admin:
            abort(403)
        try:
            conteudo = job.resultado.arquivo_saida.getvalue()
        except (ValueError, AttributeError):
            abort(404)
        return send_file(
            io.BytesIO(conteudo),
            as_attachment=True,
            download_name=job.resultado.nome_arquivo,
            mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
        )


# ==============================================================================
# Instância global (importada por gunicorn/waitress)
# ==============================================================================
app = create_app()


if __name__ == "__main__":
    print("=" * 60)
    print("Topshop Amazon System — Interface Web")
    print("=" * 60)
    print("Acesse:  http://127.0.0.1:5000/login")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)

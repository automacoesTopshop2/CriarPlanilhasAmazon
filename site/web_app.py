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
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

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
from core.processadores import ProcessadorSKU, ProcessadorASIN, ProcessadorLimpeza
from core.utils import Utilitarios

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


def _limpar_jobs_antigos(horas: int = 2) -> None:
    agora = datetime.now()
    with JOBS_LOCK:
        for jid, job in list(JOBS.items()):
            if job.status in ("done", "error"):
                idade = (agora - job.criado_em).total_seconds() / 3600
                if idade > horas:
                    JOBS.pop(jid, None)


# ==============================================================================
# Helpers de inicialização
# ==============================================================================
def _sincronizar_sharepoint_startup(app: Flask, gerenciador, cfg) -> None:
    """
    Tenta baixar a Precificação do SharePoint no startup via share-link.
    Erros são logados mas não interrompem o servidor — sistema segue com
    arquivo local antigo (se existir).
    """
    link = (gerenciador.get("sharepoint_link_precificacao") or "").strip()
    if not link:
        return  # não configurado — silencioso

    try:
        from core.sharepoint_client import SharePointClient, sincronizar_por_url
    except ImportError as e:
        app.logger.warning("SharePoint indisponível (msal não instalado?): %s", e)
        return

    cliente = SharePointClient.do_ambiente()
    if cliente is None:
        app.logger.info(
            "SharePoint link configurado mas credenciais ausentes em env "
            "(SHAREPOINT_TENANT_ID/CLIENT_ID/CLIENT_SECRET) — pulando sync."
        )
        return

    destino = cfg.arquivo_precificacao
    ok, msg = sincronizar_por_url(cliente, link, destino)
    if ok:
        app.logger.info("SharePoint sync OK: %s", msg)
    else:
        app.logger.error(
            "SharePoint sync falhou no startup (continuando com arquivo local): %s",
            msg,
        )


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
        return {
            "precificacao": _info(cfg_atual.arquivo_precificacao),
            "descricao": _info(cfg_atual.arquivo_descricao),
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

    @app.route("/sku")
    @login_required
    def page_sku():
        return render_template("sku.html", bases=_status_bases(), active="sku")

    @app.route("/asin")
    @login_required
    def page_asin():
        return render_template("asin.html", bases=_status_bases(), active="asin")

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
        bytes_template = arquivo_template.read() if arquivo_template else None
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
        job = JOBS.get(job_id)
        if not job or not job.resultado or not job.resultado.arquivo_saida:
            abort(404)
        if job.owner_id and current_user.id != job.owner_id and not current_user.is_admin:
            abort(403)
        job.resultado.arquivo_saida.seek(0)
        return send_file(
            job.resultado.arquivo_saida,
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

"""
Estado de sincronização das planilhas de precificação (e Drop-estoque).

Guarda, por planilha, o momento em que o arquivo foi editado na ORIGEM
(SharePoint `lastModifiedDateTime`) e quando o sistema o baixou por último.
Serve para:
  - exibir ao operador um alerta com a data/hora (BR) da última atualização,
    dando confiança de que está usando a base mais atualizada;
  - aplicar throttle no re-download (não baixar de novo se sincronizou há pouco).

Persistido em um JSON pequeno (separado do app_config.json para não misturar
configuração com estado de runtime). Thread-safe.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

_LOCK = threading.Lock()
_caminho: Optional[str] = None


def configurar(caminho_estado: str) -> None:
    """Define o caminho do arquivo JSON de estado (chamado no startup)."""
    global _caminho
    _caminho = caminho_estado


def _ler() -> Dict[str, dict]:
    if not _caminho or not os.path.exists(_caminho):
        return {}
    try:
        with open(_caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def _escrever(dados: Dict[str, dict]) -> None:
    if not _caminho:
        return
    try:
        pasta = os.path.dirname(os.path.abspath(_caminho)) or "."
        os.makedirs(pasta, exist_ok=True)
        with open(_caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def registrar(chave: str, *, ok: bool, source_last_modified: Optional[str],
              synced_at: str, msg: str = "") -> None:
    """Registra o resultado de uma sincronização.

    chave: identificador lógico ('precificacao', 'precificacao_full', 'drop_estoque').
    source_last_modified: ISO (UTC) do lastModified na origem, ou None.
    synced_at: ISO (UTC) do momento do download.
    """
    with _LOCK:
        dados = _ler()
        anterior = dados.get(chave, {})
        dados[chave] = {
            "ok": ok,
            # Mantém o último lastModified conhecido se a sync falhar agora.
            "source_last_modified": source_last_modified or anterior.get("source_last_modified"),
            "synced_at": synced_at,
            "msg": msg,
        }
        _escrever(dados)


def obter(chave: Optional[str] = None):
    """Retorna o registro de uma chave, ou todo o estado se chave=None."""
    dados = _ler()
    if chave is None:
        return dados
    return dados.get(chave)


def precisa_atualizar(chave: str, throttle_segundos: int) -> bool:
    """True se nunca sincronizou ou se a última sync passou do throttle."""
    reg = obter(chave)
    if not reg or not reg.get("synced_at"):
        return True
    try:
        ts = datetime.fromisoformat(str(reg["synced_at"]).replace("Z", "+00:00"))
    except Exception:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() >= throttle_segundos


def agora_utc_iso() -> str:
    """ISO (UTC) do instante atual — para gravar synced_at."""
    return datetime.now(timezone.utc).isoformat()

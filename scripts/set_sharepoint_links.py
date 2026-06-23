#!/usr/bin/env python3
"""
Define os links de compartilhamento do SharePoint no app_config.json.

Uso:
    python scripts/set_sharepoint_links.py <link_precificacao_full> <link_drop_estoque>

Cada argumento pode ser "-" para NÃO alterar aquele link (mantém o atual).
Escreve no arquivo apontado por APP_CONFIG_PATH (em prod = /data/app_config.json,
no volume do Railway). Após rodar, REINICIE o serviço para recarregar a config.

Pensado para rodar dentro do container de produção via `railway ssh`.
"""

import os
import sys

# Garante que o pacote `core` (na raiz do repo / /app) seja importável.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_manager import GerenciadorConfig  # noqa: E402


def _resumo(valor: str) -> str:
    if not valor:
        return "<vazio>"
    return (valor[:60] + "…") if len(valor) > 60 else valor


def main(argv) -> int:
    if len(argv) != 3:
        print("uso: set_sharepoint_links.py <link_full|-> <link_drop|->")
        return 2

    link_full, link_drop = argv[1].strip(), argv[2].strip()

    g = GerenciadorConfig()
    print("config:", g.caminho_arquivo)
    print("ANTES:")
    print("  full:", _resumo(g.get("sharepoint_link_precificacao_full") or ""))
    print("  drop:", _resumo(g.get("sharepoint_link_drop_estoque") or ""))

    if link_full and link_full != "-":
        g.set("sharepoint_link_precificacao_full", link_full)
    if link_drop and link_drop != "-":
        g.set("sharepoint_link_drop_estoque", link_drop)

    # Recarrega do disco para confirmar a persistência.
    g2 = GerenciadorConfig()
    print("DEPOIS:")
    print("  precificacao:", _resumo(g2.get("sharepoint_link_precificacao") or ""))
    print("  full:", _resumo(g2.get("sharepoint_link_precificacao_full") or ""))
    print("  drop:", _resumo(g2.get("sharepoint_link_drop_estoque") or ""))
    print("OK — reinicie o serviço para recarregar (railway restart).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

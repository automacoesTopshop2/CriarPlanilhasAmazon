"""
Testes da integração com a API do AgentedeTitulos como fonte da base de
Descrição (cliente HTTP + CarregadorDescricaoAPI + seleção do carregador).

Mocka `core.titulos_client` / `requests.get` — não chama a rede.
"""

from __future__ import annotations

import pytest

from core import titulos_client
from core.config import Configuracoes
from core.carregadores import CarregadorDescricao, CarregadorDescricaoAPI
from core.processadores.sku import ProcessadorSKU


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------

def test_consultar_sku_monta_url_e_headers(monkeypatch):
    monkeypatch.setenv("TITULOS_API_KEY", "tsk_x")
    monkeypatch.setenv("TITULOS_API_BASE", "https://x/api")
    cap = {}

    class R:
        status_code = 200
        ok = True
        text = ""

        def json(self):
            return {"sku": "5675", "titulo_amazon": "T"}

    def fake_get(url, headers, timeout):
        cap.update(url=url, headers=headers, timeout=timeout)
        return R()

    monkeypatch.setattr("requests.get", fake_get)
    out = titulos_client.consultar_sku("5675")
    assert cap["url"] == "https://x/api/catalog/5675"
    assert cap["headers"]["X-API-Key"] == "tsk_x"
    assert out["titulo_amazon"] == "T"


def test_consultar_sku_404_vira_none(monkeypatch):
    monkeypatch.setenv("TITULOS_API_KEY", "tsk_x")

    class R:
        status_code = 404
        ok = False
        text = ""

    monkeypatch.setattr("requests.get", lambda url, headers, timeout: R())
    assert titulos_client.consultar_sku("nao-existe") is None


def test_consultar_sku_401_vira_auth_error(monkeypatch):
    monkeypatch.setenv("TITULOS_API_KEY", "tsk_x")

    class R:
        status_code = 401
        ok = False
        text = "nope"

    monkeypatch.setattr("requests.get", lambda url, headers, timeout: R())
    with pytest.raises(titulos_client.TitulosAuthError):
        titulos_client.consultar_sku("5675")


def test_consultar_sku_sem_chave_falha(monkeypatch):
    monkeypatch.delenv("TITULOS_API_KEY", raising=False)
    with pytest.raises(titulos_client.TitulosError):
        titulos_client.consultar_sku("5675")


# ---------------------------------------------------------------------------
# CarregadorDescricaoAPI
# ---------------------------------------------------------------------------

def _row(sku="5675", **over):
    base = {
        "sku": sku,
        "titulo_amazon": "Titulo AZ",
        "titulo_mlb": "Titulo ML",
        "descricao": "Descricao do produto",
        "modelo_ref": "AUT205N",
        "ean": "7891234567890",
        "peso": "0.058",
        "comprimento": "3.1",
        "largura": "10",
        "altura": "8",
        "marcadores": ["b1", "b2", "b3", "b4", "b5"],
    }
    base.update(over)
    return base


def test_carregador_api_mapeia_campos_e_ean_vazio(monkeypatch):
    monkeypatch.setattr(titulos_client, "consultar_sku",
                        lambda s: _row() if s == "5675" else None)
    c = CarregadorDescricaoAPI(Configuracoes())
    c.carregar()
    p = c.obter_produto("5675")
    assert p is not None
    assert p.titulo == "Titulo AZ"          # prefere título Amazon
    assert p.descricao == "Descricao do produto"
    assert p.modelo == "AUT205N"
    assert p.ean == ""                      # EAN NÃO vem da API (fica c/ operador)
    assert p.peso == "0.058" and p.altura == "8"
    assert p.topicos == ["b1", "b2", "b3", "b4", "b5"]


def test_carregador_api_titulo_cai_para_ml(monkeypatch):
    monkeypatch.setattr(titulos_client, "consultar_sku",
                        lambda s: _row(titulo_amazon=""))
    p = CarregadorDescricaoAPI(Configuracoes())
    p.carregar()
    assert p.obter_produto("5675").titulo == "Titulo ML"


def test_carregador_api_sku_inexistente_none(monkeypatch):
    monkeypatch.setattr(titulos_client, "consultar_sku", lambda s: None)
    c = CarregadorDescricaoAPI(Configuracoes())
    c.carregar()
    assert c.obter_produto("ZZZ") is None


def test_carregador_api_calcula_kit_buscando_componente(monkeypatch):
    chamadas = []

    def fake(sku):
        chamadas.append(sku)
        return _row() if sku == "5675" else None

    monkeypatch.setattr(titulos_client, "consultar_sku", fake)
    c = CarregadorDescricaoAPI(Configuracoes())
    c.carregar()
    p = c.obter_produto("K2-5675")
    assert p is not None
    assert abs(float(p.peso) - 0.116) < 1e-9     # peso x2
    assert abs(float(p.altura) - 16.0) < 1e-9    # altura x2
    assert abs(float(p.comprimento) - 3.1) < 1e-9  # comp inalterado
    # buscou só o componente, não o próprio Kit
    assert "5675" in chamadas
    assert "K2-5675" not in chamadas


def test_carregador_api_nao_rebusca_sku_ausente(monkeypatch):
    chamadas = []

    def fake(sku):
        chamadas.append(sku)
        return None

    monkeypatch.setattr(titulos_client, "consultar_sku", fake)
    c = CarregadorDescricaoAPI(Configuracoes())
    c.carregar()
    c.obter_produto("9999")
    c.obter_produto("9999")
    assert chamadas.count("9999") == 1  # cacheia o "não encontrado"


# ---------------------------------------------------------------------------
# Seleção do carregador no ProcessadorBase
# ---------------------------------------------------------------------------

def test_processador_usa_xlsx_sem_chave(monkeypatch):
    """Sem TITULOS_API_KEY não há como usar a API → cai na planilha local
    (fallback de segurança; evita planilha sem descrição/medidas)."""
    monkeypatch.delenv("TITULOS_API_KEY", raising=False)
    monkeypatch.delenv("USAR_PLANILHA_DESCRICAO", raising=False)
    proc = ProcessadorSKU(Configuracoes())
    assert isinstance(proc.carregador_descricao, CarregadorDescricao)
    assert not isinstance(proc.carregador_descricao, CarregadorDescricaoAPI)


def test_processador_usa_api_com_chave(monkeypatch):
    """Com a chave, usa a API (a planilha de Descrição fica de lado)."""
    monkeypatch.setenv("TITULOS_API_KEY", "tsk_x")
    monkeypatch.delenv("USAR_PLANILHA_DESCRICAO", raising=False)
    proc = ProcessadorSKU(Configuracoes())
    assert isinstance(proc.carregador_descricao, CarregadorDescricaoAPI)


def test_processador_forca_xlsx_com_flag(monkeypatch):
    """USAR_PLANILHA_DESCRICAO=1 força a planilha mesmo com a chave presente."""
    monkeypatch.setenv("TITULOS_API_KEY", "tsk_x")
    monkeypatch.setenv("USAR_PLANILHA_DESCRICAO", "1")
    proc = ProcessadorSKU(Configuracoes())
    assert isinstance(proc.carregador_descricao, CarregadorDescricao)
    assert not isinstance(proc.carregador_descricao, CarregadorDescricaoAPI)

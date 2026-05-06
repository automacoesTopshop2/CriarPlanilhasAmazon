"""
Testes da integração SharePoint.

Não fazem chamadas reais ao Graph — usam mocks.

UUID válido para mocks: '00000000-0000-0000-0000-000000000001' (MSAL aceita
formato GUID e nomes de domínio; rejeita strings arbitrárias).
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from core.sharepoint_client import SharePointClient, SharePointError, sincronizar_arquivo

# Tenant ID em formato UUID — MSAL valida o formato no constructor
TENANT_FAKE = "00000000-0000-0000-0000-000000000001"
CLIENT_FAKE = "00000000-0000-0000-0000-000000000002"
SECRET_FAKE = "fake-secret-value"


@pytest.fixture(autouse=True)
def _isolar_app_config(monkeypatch, tmp_path):
    """
    Aponta o GerenciadorConfig para um JSON temporário por teste, evitando
    contaminação entre testes e do app_config.json real do projeto.
    """
    tmp_cfg = str(tmp_path / "app_config.json")
    monkeypatch.setattr(
        "core.config_manager.GerenciadorConfig._descobrir_caminho",
        lambda self: tmp_cfg,
    )
    yield


@pytest.fixture(autouse=True)
def _mock_msal(monkeypatch):
    """
    Mocka ConfidentialClientApplication para evitar validação online de
    authority em tenants fake. Os testes que precisam testar o token
    fazem patch específico em acquire_token_for_client.
    """
    fake_app = MagicMock()
    fake_app.acquire_token_silent.return_value = None
    fake_app.acquire_token_for_client.return_value = {"access_token": "fake-token"}
    monkeypatch.setattr(
        "core.sharepoint_client.msal.ConfidentialClientApplication",
        MagicMock(return_value=fake_app),
    )
    yield


# =============================================================================
# Cliente — parsing & construção
# =============================================================================
class TestParseSiteUrl:
    def test_parse_padrao(self):
        host, path = SharePointClient._parse_site_url(
            "https://contoso.sharepoint.com/sites/MyTeam"
        )
        assert host == "contoso.sharepoint.com"
        assert path == "/sites/MyTeam"

    def test_parse_root(self):
        host, path = SharePointClient._parse_site_url("https://contoso.sharepoint.com")
        assert host == "contoso.sharepoint.com"
        assert path == "/"

    def test_parse_remove_barra_final(self):
        host, path = SharePointClient._parse_site_url(
            "https://contoso.sharepoint.com/sites/Foo/"
        )
        assert path == "/sites/Foo"

    def test_parse_url_invalido(self):
        with pytest.raises(SharePointError):
            SharePointClient._parse_site_url("")


class TestDoAmbiente:
    def test_retorna_none_sem_credenciais(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_TENANT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_SECRET", raising=False)
        assert SharePointClient.do_ambiente() is None

    def test_cria_com_credenciais(self, monkeypatch):
        monkeypatch.setenv("SHAREPOINT_TENANT_ID", TENANT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", CLIENT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", SECRET_FAKE)
        c = SharePointClient.do_ambiente()
        assert c is not None


# =============================================================================
# Cliente — download (mockado)
# =============================================================================
class TestBaixarArquivoMock:
    def _make_client(self):
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        return c

    @patch("core.sharepoint_client.requests.get")
    def test_baixa_arquivo_com_sucesso(self, mock_get):
        mock_site = MagicMock(status_code=200)
        mock_site.json.return_value = {"id": "site-id-abc", "displayName": "Foo"}
        mock_download = MagicMock(status_code=200, content=b"FAKE_XLSX_BYTES")
        mock_get.side_effect = [mock_site, mock_download]

        c = self._make_client()
        conteudo = c.baixar_arquivo(
            "https://contoso.sharepoint.com/sites/Foo",
            "Documentos/Precificacao.xlsx",
        )
        assert conteudo == b"FAKE_XLSX_BYTES"

    @patch("core.sharepoint_client.requests.get")
    def test_arquivo_404(self, mock_get):
        mock_site = MagicMock(status_code=200)
        mock_site.json.return_value = {"id": "site-id"}
        mock_download = MagicMock(status_code=404)
        mock_get.side_effect = [mock_site, mock_download]

        c = self._make_client()
        with pytest.raises(SharePointError, match="não encontrado"):
            c.baixar_arquivo("https://x.sharepoint.com/sites/Y", "missing.xlsx")

    @patch("core.sharepoint_client.requests.get")
    def test_site_403_indica_permissao(self, mock_get):
        mock_site = MagicMock(status_code=403)
        mock_get.return_value = mock_site

        c = self._make_client()
        with pytest.raises(SharePointError, match="Sites.Selected|permiss"):
            c.baixar_arquivo("https://x.sharepoint.com/sites/Y", "file.xlsx")

    @patch("core.sharepoint_client.requests.get")
    def test_site_id_cacheado(self, mock_get):
        """Segunda chamada não faz lookup de site — usa cache."""
        mock_site = MagicMock(status_code=200)
        mock_site.json.return_value = {"id": "site-id-cache"}
        mock_dl1 = MagicMock(status_code=200, content=b"A")
        mock_dl2 = MagicMock(status_code=200, content=b"B")
        mock_get.side_effect = [mock_site, mock_dl1, mock_dl2]

        c = self._make_client()
        c.baixar_arquivo("https://x.sharepoint.com/sites/Y", "a.xlsx")
        c.baixar_arquivo("https://x.sharepoint.com/sites/Y", "b.xlsx")
        # 1 site lookup + 2 downloads = 3 calls
        assert mock_get.call_count == 3


class TestSincronizarArquivo:
    @patch("core.sharepoint_client.requests.get")
    def test_grava_arquivo_local(self, mock_get, tmp_path):
        mock_site = MagicMock(status_code=200)
        mock_site.json.return_value = {"id": "site-id"}
        mock_download = MagicMock(status_code=200, content=b"DADOS")
        mock_get.side_effect = [mock_site, mock_download]

        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        destino = str(tmp_path / "saida.xlsx")
        ok, msg = sincronizar_arquivo(
            c, "https://x.sharepoint.com/sites/Y", "file.xlsx", destino
        )
        assert ok, msg
        assert os.path.exists(destino)
        with open(destino, "rb") as f:
            assert f.read() == b"DADOS"

    @patch("core.sharepoint_client.requests.get")
    def test_retorna_false_em_erro(self, mock_get, tmp_path):
        mock_get.return_value = MagicMock(status_code=500)
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        ok, msg = sincronizar_arquivo(
            c, "https://x.sharepoint.com/sites/Y", "file.xlsx",
            str(tmp_path / "out.xlsx"),
        )
        # 500 levanta HTTPError em raise_for_status → captured como erro genérico
        assert ok is False
        assert isinstance(msg, str) and msg


# =============================================================================
# Rotas /api/config/sharepoint*
# =============================================================================
class TestRotasSharePoint:
    def test_put_config_admin(self, client, login_admin):
        r = client.put("/api/config/sharepoint", json={
            "site_url": "https://contoso.sharepoint.com/sites/Test",
            "arquivo_precificacao": "Documentos/Precificacao.xlsx",
            "sync_no_startup": True,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["sucesso"] is True
        assert data["estado"]["sharepoint"]["site_url"] == "https://contoso.sharepoint.com/sites/Test"
        assert data["estado"]["sharepoint"]["sync_no_startup"] is True

    def test_put_config_usuario_403(self, client, login_usuario):
        r = client.put("/api/config/sharepoint", json={
            "site_url": "https://contoso.sharepoint.com/sites/Test",
        })
        assert r.status_code == 403

    def test_testar_sem_credenciais_falha(self, client, login_admin, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_TENANT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_SECRET", raising=False)
        client.put("/api/config/sharepoint", json={
            "site_url": "https://contoso.sharepoint.com/sites/Test",
        })
        r = client.post("/api/config/sharepoint/testar")
        assert r.status_code == 400
        assert "Credenciais" in r.get_json().get("mensagem", "")

    def test_testar_sem_config_falha(self, client, login_admin):
        # Sem nenhuma config (site_url e/ou credenciais), retorna 400
        r = client.post("/api/config/sharepoint/testar")
        assert r.status_code == 400

    def test_sincronizar_sem_config_falha(self, client, login_admin):
        r = client.post("/api/config/sharepoint/sincronizar")
        assert r.status_code == 400

    def test_snapshot_inclui_sharepoint(self, client, login_admin):
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.get_json()
        assert "sharepoint" in data
        assert "credenciais_configuradas" in data["sharepoint"]
        assert "site_url" in data["sharepoint"]

    @patch("core.sharepoint_client.requests.get")
    def test_sincronizar_com_mock_grava_arquivo(self, mock_get, client, login_admin, app, tmp_path, monkeypatch):
        monkeypatch.setenv("SHAREPOINT_TENANT_ID", TENANT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", CLIENT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", SECRET_FAKE)

        destino = str(tmp_path / "preci.xlsx")
        with app.app_context():
            cfg = app.config["APP_CONFIG"]
            cfg.arquivo_precificacao = destino

        client.put("/api/config/sharepoint", json={
            "site_url": "https://x.sharepoint.com/sites/Y",
            "arquivo_precificacao": "Documentos/Preci.xlsx",
        })

        mock_site = MagicMock(status_code=200)
        mock_site.json.return_value = {"id": "site-x"}
        mock_dl = MagicMock(status_code=200, content=b"BYTES_FROM_SP")
        mock_get.side_effect = [mock_site, mock_dl]

        # MSAL já está mockado pelo autouse fixture
        r = client.post("/api/config/sharepoint/sincronizar")

        assert r.status_code == 200, r.get_json()
        assert os.path.exists(destino)
        with open(destino, "rb") as f:
            assert f.read() == b"BYTES_FROM_SP"

    def test_credenciais_configuradas_flag(self, client, login_admin, monkeypatch):
        # Sem credenciais
        monkeypatch.delenv("SHAREPOINT_TENANT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_SECRET", raising=False)
        r = client.get("/api/config")
        assert r.get_json()["sharepoint"]["credenciais_configuradas"] is False

        # Com credenciais
        monkeypatch.setenv("SHAREPOINT_TENANT_ID", TENANT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", CLIENT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", SECRET_FAKE)
        r = client.get("/api/config")
        assert r.get_json()["sharepoint"]["credenciais_configuradas"] is True

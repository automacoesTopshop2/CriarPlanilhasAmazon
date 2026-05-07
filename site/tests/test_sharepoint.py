"""
Testes da integração SharePoint via share-link (endpoint /shares do Graph).

Não fazem chamadas reais ao Graph — usam mocks em msal e requests.
"""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

from core.sharepoint_client import (
    SharePointClient,
    SharePointError,
    sincronizar_por_url,
)

TENANT_FAKE = "00000000-0000-0000-0000-000000000001"
CLIENT_FAKE = "00000000-0000-0000-0000-000000000002"
SECRET_FAKE = "fake-secret-value"

LINK_FAKE = (
    "https://contoso.sharepoint.com/:x:/r/sites/Foo/Documentos/Preci.xlsx"
    "?d=w1234567890abcdef&csf=1&web=1"
)


@pytest.fixture(autouse=True)
def _mock_msal(monkeypatch):
    """Mocka MSAL para evitar validação online de authority em tenants fake."""
    fake_app = MagicMock()
    fake_app.acquire_token_silent.return_value = None
    fake_app.acquire_token_for_client.return_value = {"access_token": "fake-token"}
    monkeypatch.setattr(
        "core.sharepoint_client.msal.ConfidentialClientApplication",
        MagicMock(return_value=fake_app),
    )
    yield


# =============================================================================
# Encoding de share-link
# =============================================================================
class TestEncodeShareUrl:
    def test_formato_u_bang(self):
        share_id = SharePointClient._encode_share_url(LINK_FAKE)
        assert share_id.startswith("u!")
        # base64url sem padding final
        assert "=" not in share_id

    def test_decodifica_de_volta(self):
        import base64
        share_id = SharePointClient._encode_share_url(LINK_FAKE)
        encoded = share_id[2:]  # tira "u!"
        # base64url decode (com padding restaurado)
        padding = "=" * ((4 - len(encoded) % 4) % 4)
        decoded = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        assert decoded == LINK_FAKE

    def test_link_vazio_levanta_erro(self):
        with pytest.raises(SharePointError):
            SharePointClient._encode_share_url("")


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
        assert SharePointClient.do_ambiente() is not None


# =============================================================================
# Cliente — testar_url e baixar_por_url
# =============================================================================
class TestTestarUrl:
    @patch("core.sharepoint_client.requests.get")
    def test_retorna_metadados(self, mock_get):
        mock_resp = MagicMock(status_code=200, ok=True)
        mock_resp.json.return_value = {
            "name": "Preci.xlsx",
            "size": 12345,
            "webUrl": "https://contoso.sharepoint.com/foo",
            "lastModifiedDateTime": "2025-01-01T00:00:00Z",
        }
        mock_get.return_value = mock_resp

        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        info = c.testar_url(LINK_FAKE)
        assert info["ok"] is True
        assert info["name"] == "Preci.xlsx"
        assert info["size"] == 12345

    @patch("core.sharepoint_client.requests.get")
    def test_404(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404, ok=False)
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        with pytest.raises(SharePointError, match="404|inválido"):
            c.testar_url(LINK_FAKE)

    @patch("core.sharepoint_client.requests.get")
    def test_403_indica_sites_selected(self, mock_get):
        mock_get.return_value = MagicMock(status_code=403, ok=False)
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        with pytest.raises(SharePointError, match="Sites.Selected|permiss"):
            c.testar_url(LINK_FAKE)


class TestBaixarPorUrl:
    @patch("core.sharepoint_client.requests.get")
    def test_baixa_conteudo(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, ok=True, content=b"FAKE_XLSX_BYTES"
        )
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        conteudo = c.baixar_por_url(LINK_FAKE)
        assert conteudo == b"FAKE_XLSX_BYTES"

    @patch("core.sharepoint_client.requests.get")
    def test_chama_endpoint_shares(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, ok=True, content=b"X")
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        c.baixar_por_url(LINK_FAKE)
        called_url = mock_get.call_args[0][0]
        assert "/shares/u!" in called_url
        assert called_url.endswith("/driveItem/content")


class TestSincronizarPorUrl:
    @patch("core.sharepoint_client.requests.get")
    def test_grava_arquivo_local(self, mock_get, tmp_path):
        mock_get.return_value = MagicMock(
            status_code=200, ok=True, content=b"DADOS"
        )
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        destino = str(tmp_path / "saida.xlsx")
        ok, msg = sincronizar_por_url(c, LINK_FAKE, destino)
        assert ok, msg
        assert os.path.exists(destino)
        with open(destino, "rb") as f:
            assert f.read() == b"DADOS"

    @patch("core.sharepoint_client.requests.get")
    def test_retorna_false_em_404(self, mock_get, tmp_path):
        mock_get.return_value = MagicMock(status_code=404, ok=False)
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        ok, msg = sincronizar_por_url(c, LINK_FAKE, str(tmp_path / "out.xlsx"))
        assert ok is False
        assert "404" in msg or "inválido" in msg


# =============================================================================
# Rotas /api/config/sharepoint*
# =============================================================================
class TestRotasSharePoint:
    def test_put_config_admin(self, client, login_admin):
        r = client.put("/api/config/sharepoint", json={
            "link_precificacao": LINK_FAKE,
            "sync_no_startup": True,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["sucesso"] is True
        assert data["estado"]["sharepoint"]["link_precificacao"] == LINK_FAKE
        assert data["estado"]["sharepoint"]["sync_no_startup"] is True

    def test_put_config_usuario_403(self, client, login_usuario):
        r = client.put("/api/config/sharepoint", json={"link_precificacao": LINK_FAKE})
        assert r.status_code == 403

    def test_testar_sem_credenciais_falha(self, client, login_admin, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_TENANT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_SECRET", raising=False)
        client.put("/api/config/sharepoint", json={"link_precificacao": LINK_FAKE})
        r = client.post("/api/config/sharepoint/testar")
        assert r.status_code == 400
        assert "Credenciais" in r.get_json().get("mensagem", "")

    def test_testar_sem_link_falha(self, client, login_admin):
        r = client.post("/api/config/sharepoint/testar")
        assert r.status_code == 400

    def test_sincronizar_sem_link_falha(self, client, login_admin):
        r = client.post("/api/config/sharepoint/sincronizar")
        assert r.status_code == 400

    def test_snapshot_inclui_sharepoint(self, client, login_admin):
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.get_json()
        assert "sharepoint" in data
        assert "link_precificacao" in data["sharepoint"]
        assert "credenciais_configuradas" in data["sharepoint"]

    @patch("core.sharepoint_client.requests.get")
    def test_sincronizar_com_mock_grava_arquivo(
        self, mock_get, client, login_admin, app, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("SHAREPOINT_TENANT_ID", TENANT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", CLIENT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", SECRET_FAKE)

        destino = str(tmp_path / "preci.xlsx")
        with app.app_context():
            cfg = app.config["APP_CONFIG"]
            cfg.arquivo_precificacao = destino

        client.put("/api/config/sharepoint", json={"link_precificacao": LINK_FAKE})

        mock_get.return_value = MagicMock(
            status_code=200, ok=True, content=b"BYTES_FROM_SP"
        )
        r = client.post("/api/config/sharepoint/sincronizar")
        assert r.status_code == 200, r.get_json()
        assert os.path.exists(destino)
        with open(destino, "rb") as f:
            assert f.read() == b"BYTES_FROM_SP"

    @patch("core.sharepoint_client.requests.get")
    def test_sincronizar_aceita_usuario_comum(
        self, mock_get, client, login_admin, login_usuario, app, tmp_path, monkeypatch
    ):
        """Sync deve estar aberto para qualquer usuário autenticado.
        Admin configura o link primeiro; depois usuário comum dispara o sync."""
        monkeypatch.setenv("SHAREPOINT_TENANT_ID", TENANT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", CLIENT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", SECRET_FAKE)

        destino = str(tmp_path / "preci.xlsx")
        with app.app_context():
            cfg = app.config["APP_CONFIG"]
            cfg.arquivo_precificacao = destino

        # Admin configura o link
        client.put("/api/config/sharepoint", json={"link_precificacao": LINK_FAKE})
        # Loga como usuário comum
        client.post("/logout")
        r = client.post(
            "/login",
            data={"email": "user@topshop.com.br", "senha": "SenhaForte456@"},
            follow_redirects=False,
        )
        assert r.status_code == 302

        mock_get.return_value = MagicMock(
            status_code=200, ok=True, content=b"BYTES_USR"
        )
        r = client.post("/api/config/sharepoint/sincronizar")
        assert r.status_code == 200, r.get_json()
        assert open(destino, "rb").read() == b"BYTES_USR"

    def test_credenciais_configuradas_flag(self, client, login_admin, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_TENANT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)
        monkeypatch.delenv("SHAREPOINT_CLIENT_SECRET", raising=False)
        r = client.get("/api/config")
        assert r.get_json()["sharepoint"]["credenciais_configuradas"] is False

        monkeypatch.setenv("SHAREPOINT_TENANT_ID", TENANT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", CLIENT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", SECRET_FAKE)
        r = client.get("/api/config")
        assert r.get_json()["sharepoint"]["credenciais_configuradas"] is True

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

    def test_put_config_aceita_links_full_e_drop(self, client, login_admin):
        r = client.put("/api/config/sharepoint", json={
            "link_precificacao_full": LINK_FAKE + "full",
            "link_drop_estoque": LINK_FAKE + "drop",
        })
        assert r.status_code == 200
        links = r.get_json()["estado"]["sharepoint"]["links"]
        assert links["precificacao_full"] == LINK_FAKE + "full"
        assert links["drop_estoque"] == LINK_FAKE + "drop"

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
    def test_sincronizar_chave_full_grava_arquivo_full(
        self, mock_get, client, login_admin, app, tmp_path, monkeypatch
    ):
        """`chave=precificacao_full` baixa o link Full no arquivo da Precificação Full."""
        monkeypatch.setenv("SHAREPOINT_TENANT_ID", TENANT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", CLIENT_FAKE)
        monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", SECRET_FAKE)

        destino_full = str(tmp_path / "preci_full.xlsx")
        with app.app_context():
            app.config["APP_CONFIG"].arquivo_precificacao_full = destino_full

        client.put("/api/config/sharepoint",
                   json={"link_precificacao_full": LINK_FAKE + "full"})

        mock_get.return_value = MagicMock(
            status_code=200, ok=True, content=b"FULL_BYTES"
        )
        r = client.post("/api/config/sharepoint/sincronizar",
                        json={"chave": "precificacao_full"})
        assert r.status_code == 200, r.get_json()
        assert os.path.exists(destino_full)
        with open(destino_full, "rb") as f:
            assert f.read() == b"FULL_BYTES"

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


# =============================================================================
# Folder-scan da Drop-estoque (pega o *Drop estoque*.xlsx mais recente da pasta)
# =============================================================================
class TestFolderScan:
    @patch("core.sharepoint_client.requests.get")
    def test_pega_mais_recente_da_pasta(self, mock_get, tmp_path):
        from core.sharepoint_client import sincronizar_inteligente

        def fake_get(url, **kw):
            if "/children" in url:
                return MagicMock(status_code=200, ok=True, json=lambda: {"value": [
                    {"id": "1", "name": "2026-06-22 - Drop estoque.xlsx",
                     "lastModifiedDateTime": "2026-06-22T10:00:00Z"},
                    {"id": "2", "name": "2026-06-23 - Drop estoque.xlsx",
                     "lastModifiedDateTime": "2026-06-23T10:00:00Z"},
                    {"id": "3", "name": "Outra planilha.xlsx",
                     "lastModifiedDateTime": "2026-06-24T10:00:00Z"},
                    {"id": "4", "name": "2026-06-24 - Drop estoque.pdf",
                     "lastModifiedDateTime": "2026-06-24T11:00:00Z"},
                ]})
            if "/content" in url:
                return MagicMock(status_code=200, ok=True, content=b"DROP_BYTES")
            # driveItem do arquivo apontado -> parentReference
            return MagicMock(status_code=200, ok=True,
                             json=lambda: {"parentReference": {"driveId": "D", "id": "P"}})

        mock_get.side_effect = fake_get
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        destino = str(tmp_path / "drop.xlsx")
        ok, msg, lm = sincronizar_inteligente(
            c, LINK_FAKE, destino, pasta_contem="drop estoque"
        )
        assert ok, msg
        # Escolhe o .xlsx "drop estoque" mais recente (id 2) — ignora o .pdf e o não-correspondente.
        assert lm == "2026-06-23T10:00:00Z"
        with open(destino, "rb") as f:
            assert f.read() == b"DROP_BYTES"

    @patch("core.sharepoint_client.requests.get")
    def test_fallback_para_link_direto_quando_pasta_falha(self, mock_get, tmp_path):
        from core.sharepoint_client import sincronizar_inteligente

        def fake_get(url, **kw):
            # Lista da pasta falha (403) -> deve cair no fallback de link direto.
            if "/children" in url:
                return MagicMock(status_code=403, ok=False, json=lambda: {})
            if "/content" in url:
                return MagicMock(status_code=200, ok=True, content=b"DIRETO_BYTES")
            # driveItem (resolve parent p/ tentar a pasta, e tb usado no link direto)
            return MagicMock(status_code=200, ok=True,
                             json=lambda: {"parentReference": {"driveId": "D", "id": "P"},
                                           "name": "x.xlsx", "lastModifiedDateTime": "2026-06-23T09:00:00Z"})

        mock_get.side_effect = fake_get
        c = SharePointClient(TENANT_FAKE, CLIENT_FAKE, SECRET_FAKE)
        destino = str(tmp_path / "drop.xlsx")
        ok, msg, lm = sincronizar_inteligente(
            c, LINK_FAKE, destino, pasta_contem="drop estoque"
        )
        assert ok, msg
        assert "fallback" in msg.lower()
        with open(destino, "rb") as f:
            assert f.read() == b"DIRETO_BYTES"

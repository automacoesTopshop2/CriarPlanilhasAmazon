"""Testes da página de configurações e API CRUD."""

from auth import db
from core.config_manager import GerenciadorConfig


class TestPaginaConfig:
    def test_admin_acessa(self, client, login_admin):
        r = client.get("/configuracoes")
        assert r.status_code == 200
        assert b"Valores Fixos" in r.data

    def test_usuario_proibido(self, client, login_usuario):
        r = client.get("/configuracoes")
        assert r.status_code == 403


class TestApiConfigGet:
    def test_get_snapshot(self, client, login_admin):
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.get_json()
        assert "arquivos" in data
        assert "valores_fixos" in data
        assert "mapa_colunas" in data
        assert "mapa_prefixo" in data


class TestValoresFixos:
    def test_adicionar_valor_fixo(self, client, app, login_admin):
        r = client.post("/api/config/valores-fixos", json={
            "coluna": "Coluna Custom",
            "valor": "Valor Custom",
        })
        assert r.status_code == 200
        # persistido
        g = app.config["CONFIG_MANAGER"]
        assert g.valores_fixos_customizados().get("Coluna Custom") == "Valor Custom"

    def test_editar_valor_fixo(self, client, app, login_admin):
        client.post("/api/config/valores-fixos", json={
            "coluna": "X", "valor": "antigo",
        })
        r = client.put("/api/config/valores-fixos/X", json={
            "nome_novo": "Y", "valor": "novo",
        })
        assert r.status_code == 200
        g = app.config["CONFIG_MANAGER"]
        custom = g.valores_fixos_customizados()
        assert "X" not in custom
        assert custom.get("Y") == "novo"

    def test_remover_valor_fixo(self, client, app, login_admin):
        client.post("/api/config/valores-fixos", json={
            "coluna": "Remover", "valor": "x",
        })
        r = client.delete("/api/config/valores-fixos/Remover")
        assert r.status_code == 200
        g = app.config["CONFIG_MANAGER"]
        assert "Remover" not in g.valores_fixos_customizados()

    def test_alteracao_aplica_no_app_config(self, client, app, login_admin):
        client.post("/api/config/valores-fixos", json={
            "coluna": "Tipo de produto",  # já tem default
            "valor": "AUDIO_OR_VIDEO_OVERRIDE",
        })
        cfg = app.config["APP_CONFIG"]
        assert cfg.valores_fixos_padrao["Tipo de produto"] == "AUDIO_OR_VIDEO_OVERRIDE"


class TestMapaColunas:
    def test_adicionar_sinonimo(self, client, app, login_admin):
        r = client.post("/api/config/mapa-colunas/sku", json={"sinonimo": "Cod_Produto"})
        assert r.status_code == 200
        cfg = app.config["APP_CONFIG"]
        assert "Cod_Produto" in cfg.mapa_colunas_descricao["sku"]

    def test_remover_sinonimo(self, client, app, login_admin):
        client.post("/api/config/mapa-colunas/sku", json={"sinonimo": "TempCol"})
        r = client.delete("/api/config/mapa-colunas/sku/TempCol")
        assert r.status_code == 200

    def test_adicionar_chave_logica_nova(self, client, app, login_admin):
        r = client.post("/api/config/mapa-colunas/novo_campo", json={"sinonimo": "Sin1"})
        assert r.status_code == 200
        g = app.config["CONFIG_MANAGER"]
        assert "novo_campo" in g.mapa_colunas_descricao()

    def test_remover_chave_inteira(self, client, app, login_admin):
        client.post("/api/config/mapa-colunas/temp", json={"sinonimo": "x"})
        r = client.delete("/api/config/mapa-colunas/temp")
        assert r.status_code == 200
        g = app.config["CONFIG_MANAGER"]
        assert "temp" not in g.mapa_colunas_descricao()

    def test_sinonimo_vazio_recusa(self, client, app, login_admin):
        r = client.post("/api/config/mapa-colunas/sku", json={"sinonimo": ""})
        assert r.status_code == 400


class TestPrefixos:
    def test_adicionar_prefixo(self, client, app, login_admin):
        r = client.post("/api/config/prefixos", json={
            "prefixo": "NEW", "conta": "NovaConta",
        })
        assert r.status_code == 200
        cfg = app.config["APP_CONFIG"]
        # auto-adiciona o '-'
        assert cfg.mapa_prefixo_conta.get("NEW-") == "NovaConta"

    def test_prefixo_uppercase(self, client, app, login_admin):
        r = client.post("/api/config/prefixos", json={
            "prefixo": "nova-", "conta": "Conta",
        })
        assert r.status_code == 200
        g = app.config["CONFIG_MANAGER"]
        assert "NOVA-" in g.mapa_prefixo_conta()

    def test_remover_prefixo(self, client, app, login_admin):
        client.post("/api/config/prefixos", json={
            "prefixo": "DEL-", "conta": "X",
        })
        r = client.delete("/api/config/prefixos/DEL-")
        assert r.status_code == 200

    def test_campos_obrigatorios(self, client, login_admin):
        r = client.post("/api/config/prefixos", json={"prefixo": "", "conta": ""})
        assert r.status_code == 400


class TestArquivosUrl:
    def test_atualizar_arquivos(self, client, app, login_admin):
        r = client.put("/api/config/arquivos", json={
            "arquivo_precificacao": "outro.xlsx",
            "url_base_imagens": "https://novo.example.com",
        })
        assert r.status_code == 200
        g = app.config["CONFIG_MANAGER"]
        assert g.get("arquivo_precificacao") == "outro.xlsx"
        assert g.get("url_base_imagens") == "https://novo.example.com"


class TestOneDrive:
    def test_atualizar_lista(self, client, app, login_admin):
        r = client.put("/api/config/onedrive", json={
            "caminhos": ["A.xlsx", "B.xlsx"],
        })
        assert r.status_code == 200
        g = app.config["CONFIG_MANAGER"]
        assert g.caminhos_onedrive() == ["A.xlsx", "B.xlsx"]


class TestRequerAdmin:
    def test_post_valor_fixo_como_usuario_403(self, client, login_usuario):
        r = client.post("/api/config/valores-fixos", json={"coluna": "x", "valor": "y"})
        assert r.status_code == 403

    def test_get_config_como_usuario_403(self, client, login_usuario):
        r = client.get("/api/config")
        assert r.status_code == 403


class TestGerenciadorConfigCRUD:
    """Testes unitários do GerenciadorConfig (sem Flask)."""

    def test_adicionar_sinonimo_no_set(self, tmp_path):
        path = str(tmp_path / "test_config.json")
        g = GerenciadorConfig(caminho_arquivo=path)
        g.adicionar_sinonimo_coluna("sku", "MeuSKU")
        g.adicionar_sinonimo_coluna("sku", "MeuSKU")  # idempotente
        assert g.mapa_colunas_descricao()["sku"].count("MeuSKU") == 1

    def test_persiste_e_carrega(self, tmp_path):
        path = str(tmp_path / "config.json")
        g = GerenciadorConfig(caminho_arquivo=path)
        g.adicionar_prefixo("ZZZ", "ContaZZZ")
        # nova instância — deve ler do disco
        g2 = GerenciadorConfig(caminho_arquivo=path)
        assert g2.mapa_prefixo_conta()["ZZZ-"] == "ContaZZZ"

    def test_prefixo_auto_dash(self, tmp_path):
        path = str(tmp_path / "config.json")
        g = GerenciadorConfig(caminho_arquivo=path)
        g.adicionar_prefixo("ABC", "X")
        assert "ABC-" in g.mapa_prefixo_conta()
        assert "ABC" not in g.mapa_prefixo_conta()

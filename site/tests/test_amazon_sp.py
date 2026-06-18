"""
Testes do cliente SP-API + módulo de criação de anúncios (amazon_listings).

Tudo mockado — não chama a Amazon. Valida montagem de payload, modo de
validação e leitura de credenciais/token.
"""

from __future__ import annotations

import pytest

from core import amazon_sp_client as sp
from core import amazon_listings as al


@pytest.fixture(autouse=True)
def _env_amazon(monkeypatch):
    monkeypatch.setenv("AMAZON_LWA_CLIENT_ID", "amzn1.application-oa2-client.abc")
    monkeypatch.setenv("AMAZON_LWA_CLIENT_SECRET", "amzn1.oa2-cs.v1.def")
    monkeypatch.setenv("AMAZON_SP_REFRESH_TOKEN", "Atzr|fake")
    monkeypatch.setenv("AMAZON_SELLER_ID", "SELLER123")
    monkeypatch.setenv("AMAZON_MARKETPLACE_ID", "A2Q3Y263D00KWC")
    # zera cache de token entre testes
    sp._token_cache["valor"] = None
    sp._token_cache["expira_em"] = 0.0
    yield


# ---------------------------------------------------------------------------
# Cliente: token LWA + request
# ---------------------------------------------------------------------------

def test_access_token_usa_refresh_e_cacheia(monkeypatch):
    chamadas = []

    class R:
        status_code = 200
        ok = True
        text = ""

        def json(self):
            return {"access_token": "Atza|tok", "expires_in": 3600}

    def fake_post(url, data, headers, timeout):
        chamadas.append((url, data))
        return R()

    monkeypatch.setattr("requests.post", fake_post)
    t1 = sp._access_token()
    t2 = sp._access_token()  # deve vir do cache
    assert t1 == "Atza|tok" and t2 == "Atza|tok"
    assert len(chamadas) == 1
    url, data = chamadas[0]
    assert url == sp.LWA_TOKEN_URL
    assert data["grant_type"] == "refresh_token"
    assert data["refresh_token"] == "Atzr|fake"
    assert data["client_id"].startswith("amzn1.application-oa2-client")


def test_put_listing_inclui_mode_validation(monkeypatch):
    monkeypatch.setattr(sp, "_access_token", lambda forcar=False: "tok")
    cap = {}

    class R:
        status_code = 200
        ok = True
        text = ""

        def json(self):
            return {"sku": "X", "status": "ACCEPTED", "issues": []}

    def fake_request(method, url, headers, params, json, timeout):
        cap.update(method=method, url=url, headers=headers, params=params, json=json)
        return R()

    monkeypatch.setattr("requests.request", fake_request)
    sp.put_listing("MEU-SKU", {"productType": "PRODUCT"}, mode="VALIDATION_PREVIEW")
    assert cap["method"] == "PUT"
    assert "/listings/2021-08-01/items/SELLER123/MEU-SKU" in cap["url"]
    assert cap["params"]["mode"] == "VALIDATION_PREVIEW"
    assert cap["params"]["marketplaceIds"] == "A2Q3Y263D00KWC"
    assert cap["headers"]["x-amz-access-token"] == "tok"


def test_credenciais_ok(monkeypatch):
    assert sp.credenciais_ok() is True
    monkeypatch.delenv("AMAZON_SP_REFRESH_TOKEN", raising=False)
    assert sp.credenciais_ok() is False


# ---------------------------------------------------------------------------
# Fluxo por ASIN (oferta sobre item existente)
# ---------------------------------------------------------------------------

def test_oferta_por_asin_monta_offer_only(monkeypatch):
    cap = {}

    def fake_put(sku, body, *, mode="VALIDATION_PREVIEW", included_data="issues,status"):
        cap.update(sku=sku, body=body, mode=mode)
        return {"sku": sku, "status": "ACCEPTED", "issues": []}

    monkeypatch.setattr(sp, "put_listing", fake_put)

    al.criar_oferta_por_asin(sku="TACNAR-1", asin="B0ABC12345",
                             preco=99.9, quantidade=5, product_type="HEADPHONES")
    assert cap["sku"] == "TACNAR-1"
    assert cap["mode"] == "VALIDATION_PREVIEW"
    body = cap["body"]
    assert body["requirements"] == "LISTING_OFFER_ONLY"
    assert body["productType"] == "HEADPHONES"
    attrs = body["attributes"]
    assert attrs["merchant_suggested_asin"][0]["value"] == "B0ABC12345"
    assert attrs["condition_type"][0]["value"] == "new_new"
    assert attrs["purchasable_offer"][0]["our_price"][0]["schedule"][0]["value_with_tax"] == 99.9
    assert attrs["fulfillment_availability"][0]["quantity"] == 5


def test_oferta_por_asin_descobre_product_type(monkeypatch):
    monkeypatch.setattr(sp, "buscar_catalogo_por_asin",
                        lambda asin, **k: {"summaries": [{"productType": "TOYS_AND_GAMES"}]})
    cap = {}
    monkeypatch.setattr(sp, "put_listing",
                        lambda sku, body, **k: cap.update(body=body) or {"issues": []})
    al.criar_oferta_por_asin(sku="S1", asin="B0X", preco=10.0)
    assert cap["body"]["productType"] == "TOYS_AND_GAMES"


def test_oferta_por_asin_sem_asin_falha():
    with pytest.raises(sp.AmazonSPError):
        al.criar_oferta_por_asin(sku="S1", asin="", preco=10.0, product_type="X")


# ---------------------------------------------------------------------------
# Fluxo por SKU (produto novo)
# ---------------------------------------------------------------------------

def test_produto_novo_monta_atributos(monkeypatch):
    cap = {}
    monkeypatch.setattr(sp, "put_listing",
                        lambda sku, body, **k: cap.update(sku=sku, body=body, mode=k.get("mode")) or {"issues": []})

    al.criar_produto_por_sku(
        sku="TACNAR-NOVO-1",
        product_type="HEADPHONES",
        titulo="Fone Bluetooth X",
        descricao="Um fone muito bom",
        bullets=["b1", "b2", "b3", "b4", "b5", "b6"],  # deve truncar p/ 5
        marca="1Hora",
        ean="7891234567890",
        preco=129.9,
        quantidade=3,
        peso_kg="0.058",
        comprimento_cm="3.1",
        largura_cm="10",
        altura_cm="8",
        imagem_principal_url="https://img/x_01.jpg",
    )
    body = cap["body"]
    assert body["requirements"] == "LISTING"            # tem preço -> produto + oferta
    attrs = body["attributes"]
    assert attrs["item_name"][0]["value"] == "Fone Bluetooth X"
    assert attrs["brand"][0]["value"] == "1Hora"
    assert attrs["product_description"][0]["value"].startswith("Um fone")
    assert len(attrs["bullet_point"]) == 5              # truncado
    assert attrs["externally_assigned_product_identifier"][0]["value"] == "7891234567890"
    assert attrs["item_package_weight"][0]["value"] == 0.058
    assert attrs["item_package_dimensions"][0]["length"]["value"] == 3.1
    assert attrs["main_product_image_locator"][0]["media_location"] == "https://img/x_01.jpg"
    assert attrs["purchasable_offer"][0]["our_price"][0]["schedule"][0]["value_with_tax"] == 129.9


def test_produto_novo_sem_preco_vira_product_only(monkeypatch):
    cap = {}
    monkeypatch.setattr(sp, "put_listing",
                        lambda sku, body, **k: cap.update(body=body) or {"issues": []})
    al.criar_produto_por_sku(sku="S1", product_type="PRODUCT", titulo="T")
    assert cap["body"]["requirements"] == "LISTING_PRODUCT_ONLY"
    assert "purchasable_offer" not in cap["body"]["attributes"]


def test_produto_novo_atributos_extra_sobrescreve(monkeypatch):
    cap = {}
    monkeypatch.setattr(sp, "put_listing",
                        lambda sku, body, **k: cap.update(body=body) or {"issues": []})
    al.criar_produto_por_sku(sku="S1", product_type="PRODUCT", titulo="T",
                             atributos_extra={"country_of_origin": [{"value": "BR"}]})
    assert cap["body"]["attributes"]["country_of_origin"][0]["value"] == "BR"


def test_resumo_issues():
    resp = {
        "sku": "S1", "status": "ACCEPTED", "submissionId": "sub1",
        "issues": [
            {"code": "90001", "message": "faltou X", "severity": "ERROR"},
            {"code": "80001", "message": "cuidado Y", "severity": "WARNING"},
        ],
    }
    r = al.resumo_issues(resp)
    assert r["total_erros"] == 1 and r["total_avisos"] == 1
    assert "90001: faltou X" in r["erros"]

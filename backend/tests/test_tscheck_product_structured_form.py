"""Criterion: Product form is structured — aliases, optional sizes, additionals with
aliases, and an uploaded photo (data URL) are all persisted and returned by the API."""
import random

from .conftest import api_url


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={
            "store_name": f"tscheck-{slug}-store-{random.randint(1000, 9999)}",
            "email": email,
            "password": "Teste12345",
            "name": "Tester",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.cookies


def test_product_with_sizes_additionals_aliases_and_photo(client):
    cookies = _register_store(client, "prodform")
    tiny_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    payload = {
        "name": "tscheck-Marmita Especial",
        "category": "Marmita",
        "price": 20.0,
        "description": "",
        "active": True,
        "image_url": tiny_png,
        "aliases": ["marmitex", "quentinha"],
        "sizes": [{"name": "P", "price": 18.9}, {"name": "G", "price": 27.9}],
        "additionals": [{"name": "Ovo frito", "price": 3.0, "aliases": ["ovinho"]}],
        "stock": None,
    }
    resp = client.post("/products", json=payload, cookies=cookies)
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["aliases"] == ["marmitex", "quentinha"]
    assert created["sizes"] == [{"name": "P", "price": 18.9}, {"name": "G", "price": 27.9}]
    assert created["additionals"][0]["name"] == "Ovo frito"
    assert created["additionals"][0]["aliases"] == ["ovinho"]
    assert created["image_url"] == tiny_png
    product_id = created["product_id"]

    listing = client.get("/products", cookies=cookies)
    assert listing.status_code == 200, listing.text
    found = next((p for p in listing.json() if p["product_id"] == product_id), None)
    assert found is not None, "created product not returned by GET /products"
    assert found["aliases"] == ["marmitex", "quentinha"]
    assert found["additionals"][0]["aliases"] == ["ovinho"]


def test_product_without_sizes_is_optional(client):
    cookies = _register_store(client, "prodformnosize")
    payload = {
        "name": "tscheck-Suco Natural",
        "category": "Bebida",
        "price": 8.5,
        "description": "",
        "active": True,
        "image_url": "",
        "aliases": [],
        "sizes": [],
        "additionals": [],
        "stock": 10,
    }
    resp = client.post("/products", json=payload, cookies=cookies)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sizes"] == []
    assert body["stock"] == 10

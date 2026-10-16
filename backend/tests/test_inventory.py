"""
Automated tests for critical stock operations and business rules
(version for the ORIGINAL main.py, before the returns / receive / trends update).

Uses a temporary in-memory SQLite database, so your real data is never touched.

Run from the backend folder:   pytest -v
"""
import itertools
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Make `import main`, `import models` work when pytest runs from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402

from database import get_db  # noqa: E402

try:
    from database import Base  # noqa: E402
except ImportError:
    from models import Base  # noqa: E402


# ---------------------------------------------------------------------
# Test setup
# ---------------------------------------------------------------------

@pytest.fixture()
def client():
    """A test client wired to a brand-new in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


_counter = itertools.count(1)


def make_supplier(client, lead_time_days=7):
    n = next(_counter)
    r = client.post("/suppliers", json={"name": f"Supplier {n}",
                                        "lead_time_days": lead_time_days})
    assert r.status_code == 200, r.text
    return r.json()


def make_product(client, stock=10, minimum_stock=5, supplier_id=None,
                 purchase_price=50, selling_price=80):
    n = next(_counter)
    r = client.post("/products", json={
        "name": f"Product {n}",
        "sku": f"SKU-{n}",
        "purchase_price": purchase_price,
        "selling_price": selling_price,
        "current_stock": stock,
        "minimum_stock": minimum_stock,
        "supplier_id": supplier_id,
    })
    assert r.status_code == 200, r.text
    return r.json()


def stock_of(client, product_id):
    return client.get(f"/products/{product_id}").json()["current_stock"]


def sell(client, product_id, quantity, unit_price=80):
    return client.post("/sales", json={"product_id": product_id,
                                       "quantity": quantity,
                                       "unit_price": unit_price})


def assert_stock_matches_history(client):
    """The stock history total must equal current_stock for every product."""
    r = client.get("/analytics/stock-consistency")
    assert r.status_code == 200
    assert r.json()["mismatch_count"] == 0, r.json()["mismatches"]


# ---------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------

def test_opening_stock_is_recorded_in_history(client):
    p = make_product(client, stock=10)
    moves = client.get(f"/products/{p['id']}/movements").json()
    assert len(moves) == 1
    assert moves[0]["quantity_change"] == 10
    assert_stock_matches_history(client)


def test_selling_price_below_cost_is_rejected(client):
    r = client.post("/products", json={
        "name": "Bad price", "sku": "BAD-1",
        "purchase_price": 100, "selling_price": 50,
    })
    assert r.status_code == 400


def test_duplicate_sku_is_rejected(client):
    p = make_product(client)
    r = client.post("/products", json={
        "name": "Copy", "sku": p["sku"],
        "purchase_price": 10, "selling_price": 20,
    })
    assert r.status_code == 409


def test_editing_stock_on_product_form_updates_stock_and_history(client):
    p = make_product(client, stock=10)
    payload = {
        "name": p["name"], "sku": p["sku"],
        "purchase_price": 50, "selling_price": 80,
        "current_stock": 25, "minimum_stock": 5,
    }
    r = client.put(f"/products/{p['id']}", json=payload)
    assert r.status_code == 200
    assert stock_of(client, p["id"]) == 25
    assert_stock_matches_history(client)


def test_editing_product_details_without_changing_stock(client):
    p = make_product(client, stock=10)
    payload = {
        "name": "Renamed", "sku": p["sku"],
        "purchase_price": 50, "selling_price": 80,
        "current_stock": 10, "minimum_stock": 5,
    }
    r = client.put(f"/products/{p['id']}", json=payload)
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert stock_of(client, p["id"]) == 10


# ---------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------

def test_sale_reduces_stock(client):
    p = make_product(client, stock=10)
    r = sell(client, p["id"], 3)
    assert r.status_code == 200
    assert stock_of(client, p["id"]) == 7
    assert_stock_matches_history(client)


def test_cannot_sell_more_than_stock(client):
    p = make_product(client, stock=5)
    r = sell(client, p["id"], 10)
    assert r.status_code == 400
    assert stock_of(client, p["id"]) == 5


def test_cannot_sell_deactivated_product(client):
    p = make_product(client, stock=5)
    client.patch(f"/products/{p['id']}/deactivate")
    r = sell(client, p["id"], 1)
    assert r.status_code == 400


def test_editing_a_sale_adjusts_stock(client):
    p = make_product(client, stock=10)
    sale = sell(client, p["id"], 3).json()
    assert stock_of(client, p["id"]) == 7

    r = client.put(f"/sales/{sale['id']}", json={
        "product_id": p["id"], "quantity": 5, "unit_price": 80})
    assert r.status_code == 200
    assert stock_of(client, p["id"]) == 5
    assert_stock_matches_history(client)


def test_deleting_a_sale_restores_stock(client):
    p = make_product(client, stock=10)
    sale = sell(client, p["id"], 4).json()
    assert stock_of(client, p["id"]) == 6

    r = client.delete(f"/sales/{sale['id']}")
    assert r.status_code == 200
    assert stock_of(client, p["id"]) == 10
    assert_stock_matches_history(client)


def test_bulk_sale_is_all_or_nothing(client):
    ok = make_product(client, stock=5)
    short = make_product(client, stock=1)

    r = client.post("/sales-bulk", json={"items": [
        {"product_id": ok["id"], "quantity": 2, "unit_price": 80},
        {"product_id": short["id"], "quantity": 5, "unit_price": 80},
    ]})
    assert r.status_code == 400
    # Neither product changed.
    assert stock_of(client, ok["id"]) == 5
    assert stock_of(client, short["id"]) == 1


def test_bulk_sale_success_reduces_every_product(client):
    a = make_product(client, stock=5)
    b = make_product(client, stock=8)
    r = client.post("/sales-bulk", json={"items": [
        {"product_id": a["id"], "quantity": 2, "unit_price": 80},
        {"product_id": b["id"], "quantity": 3, "unit_price": 80},
    ]})
    assert r.status_code == 200
    assert stock_of(client, a["id"]) == 3
    assert stock_of(client, b["id"]) == 5
    assert_stock_matches_history(client)


# ---------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------

def test_purchase_increases_stock(client):
    s = make_supplier(client)
    p = make_product(client, stock=2)
    r = client.post("/purchases", json={
        "supplier_id": s["id"], "product_id": p["id"],
        "quantity": 10, "unit_cost": 50})
    assert r.status_code == 200
    assert stock_of(client, p["id"]) == 12
    assert_stock_matches_history(client)


def test_purchase_with_unknown_supplier_is_rejected(client):
    p = make_product(client)
    r = client.post("/purchases", json={
        "supplier_id": 9999, "product_id": p["id"],
        "quantity": 1, "unit_cost": 50})
    assert r.status_code == 404


def test_bulk_purchase_increases_every_product(client):
    s = make_supplier(client)
    a = make_product(client, stock=1)
    b = make_product(client, stock=2)
    r = client.post("/purchases-bulk", json={
        "supplier_id": s["id"],
        "items": [
            {"product_id": a["id"], "quantity": 5, "unit_cost": 50},
            {"product_id": b["id"], "quantity": 7, "unit_cost": 50},
        ]})
    assert r.status_code == 200
    assert stock_of(client, a["id"]) == 6
    assert stock_of(client, b["id"]) == 9
    assert_stock_matches_history(client)


def test_deleting_a_purchase_removes_its_stock(client):
    s = make_supplier(client)
    p = make_product(client, stock=2)
    purchase = client.post("/purchases", json={
        "supplier_id": s["id"], "product_id": p["id"],
        "quantity": 10, "unit_cost": 50}).json()
    assert stock_of(client, p["id"]) == 12

    r = client.delete(f"/purchases/{purchase['purchase_id']}")
    assert r.status_code == 200
    assert stock_of(client, p["id"]) == 2
    assert_stock_matches_history(client)


# ---------------------------------------------------------------------
# Manual stock adjustments
# ---------------------------------------------------------------------

def test_adjustment_cannot_take_stock_below_zero(client):
    p = make_product(client, stock=3)
    r = client.post(f"/products/{p['id']}/adjust-stock",
                    json={"quantity_change": -10, "reason": "Damaged goods"})
    assert r.status_code == 400
    assert stock_of(client, p["id"]) == 3


def test_adjustment_needs_a_reason(client):
    p = make_product(client, stock=3)
    r = client.post(f"/products/{p['id']}/adjust-stock",
                    json={"quantity_change": -1, "reason": "  "})
    assert r.status_code == 422


def test_valid_adjustment_is_logged(client):
    p = make_product(client, stock=10)
    r = client.post(f"/products/{p['id']}/adjust-stock",
                    json={"quantity_change": -2, "reason": "Damaged goods"})
    assert r.status_code == 200
    assert stock_of(client, p["id"]) == 8
    assert_stock_matches_history(client)


# ---------------------------------------------------------------------
# Purchase orders and reorder recommendations
# ---------------------------------------------------------------------

def test_creating_a_purchase_order_does_not_change_stock(client):
    s = make_supplier(client)
    p = make_product(client, stock=2, supplier_id=s["id"])
    r = client.post("/purchase-orders", json={
        "product_id": p["id"], "supplier_id": s["id"], "quantity": 20})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert stock_of(client, p["id"]) == 2


def test_purchase_order_for_unknown_product_is_rejected(client):
    s = make_supplier(client)
    r = client.post("/purchase-orders", json={
        "product_id": 9999, "supplier_id": s["id"], "quantity": 5})
    assert r.status_code == 404


def test_out_of_stock_product_gets_a_reorder_recommendation(client):
    s = make_supplier(client, lead_time_days=7)
    p = make_product(client, stock=0, minimum_stock=5, supplier_id=s["id"])
    recs = client.get("/reorder/recommendations").json()["recommendations"]
    rec = next((r for r in recs if r["product_id"] == p["id"]), None)
    assert rec is not None
    assert rec["recommended_quantity"] == 5
    assert rec["urgency"] == "high"


def test_well_stocked_product_gets_no_reorder_recommendation(client):
    s = make_supplier(client)
    p = make_product(client, stock=500, minimum_stock=5, supplier_id=s["id"])
    recs = client.get("/reorder/recommendations").json()["recommendations"]
    assert all(r["product_id"] != p["id"] for r in recs)


def test_reorder_window_is_validated(client):
    assert client.get("/reorder/recommendations?window=1").status_code == 400
    assert client.get("/reorder/recommendations?window=500").status_code == 400


# ---------------------------------------------------------------------
# Low stock and insights
# ---------------------------------------------------------------------

def test_low_stock_alert_lists_products_at_or_below_minimum(client):
    low = make_product(client, stock=2, minimum_stock=5)
    make_product(client, stock=50, minimum_stock=5)
    data = client.get("/alerts/low-stock").json()
    assert data["total_alerts"] == 1
    assert data["products"][0]["id"] == low["id"]


def test_insights_endpoint_works_on_an_empty_database(client):
    r = client.get("/insights")
    assert r.status_code == 200
    assert len(r.json()["insights"]) > 0


# ---------------------------------------------------------------------
# Final safety net
# ---------------------------------------------------------------------

def test_stock_always_matches_history_after_a_mix_of_operations(client):
    s = make_supplier(client)
    p = make_product(client, stock=10, supplier_id=s["id"])

    sell(client, p["id"], 3)
    client.post("/purchases", json={
        "supplier_id": s["id"], "product_id": p["id"],
        "quantity": 6, "unit_cost": 50})
    client.post(f"/products/{p['id']}/adjust-stock",
                json={"quantity_change": -2, "reason": "Damaged goods"})

    # 10 - 3 + 6 - 2 = 11
    assert stock_of(client, p["id"]) == 11
    assert_stock_matches_history(client)

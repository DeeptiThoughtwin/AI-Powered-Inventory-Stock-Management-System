import random
from datetime import datetime, timedelta, timezone
from database import SessionLocal
from models import Product, Supplier, Purchase, Sale, StockMovement

random.seed(42)
db = SessionLocal()

if db.query(StockMovement).filter(StockMovement.reason == "Sample history").count():
    print("Sample history already added. Nothing to do.")
    raise SystemExit

supplier = db.query(Supplier).first()
products = db.query(Product).filter(Product.is_active.is_(True)).all()
if supplier is None or not products:
    print("Need at least one supplier and one product first.")
    raise SystemExit

now = datetime.now(timezone.utc)

for product in products:
    plan = []
    for days_ago in range(30, 0, -1):
        qty = random.choice([0, 0, 1, 1, 2, 3])
        if qty:
            plan.append((days_ago, qty))
    total = sum(q for _, q in plan)
    if total == 0:
        continue

    start = now - timedelta(days=31)
    purchase = Purchase(
        supplier_id=supplier.id, product_id=product.id, quantity=total,
        unit_cost=product.purchase_price,
        total_cost=round(float(product.purchase_price) * total, 2),
        purchase_date=start,
    )
    db.add(purchase)
    db.flush()
    db.add(StockMovement(product_id=product.id, quantity_change=total,
                         movement_type="purchase", reference_type="purchase",
                         reference_id=purchase.id, reason="Sample history",
                         created_at=start))

    for days_ago, qty in plan:
        when = now - timedelta(days=days_ago)
        sale = Sale(
            product_id=product.id, quantity=qty, unit_price=product.selling_price,
            total_amount=round(float(product.selling_price) * qty, 2), sale_date=when,
        )
        db.add(sale)
        db.flush()
        db.add(StockMovement(product_id=product.id, quantity_change=-qty,
                             movement_type="sale", reference_type="sale",
                             reference_id=sale.id, reason="Sample history",
                             created_at=when))

db.commit()
print("Sample history added.")
from sqlalchemy import text
from database import SessionLocal, Base
import models  # noqa: F401  (makes the new tables known)

db = SessionLocal()
engine = db.get_bind()

# 1. Create new tables (stock_movements, purchase_orders) if missing
Base.metadata.create_all(bind=engine)

# 2. Add new columns to old tables if missing
for sql in [
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_id INTEGER REFERENCES suppliers(id)",
    "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS lead_time_days INTEGER NOT NULL DEFAULT 7",
    "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS reference VARCHAR(40)",
    "ALTER TABLE sales ADD COLUMN IF NOT EXISTS reference VARCHAR(40)",
]:
    db.execute(text(sql))
db.commit()

# 3. Database-level rule: stock can never be negative
try:
    db.execute(text(
        "ALTER TABLE products ADD CONSTRAINT products_stock_not_negative "
        "CHECK (current_stock >= 0)"
    ))
    db.commit()
except Exception:
    db.rollback()
    print("Stock check constraint already exists, skipping.")

# 4. One 'opening balance' history row per product (only the first time)
count = db.execute(text("SELECT COUNT(*) FROM stock_movements")).scalar()
if count == 0:
    db.execute(text(
        "INSERT INTO stock_movements (product_id, quantity_change, movement_type, reason) "
        "SELECT id, current_stock, 'adjustment', "
        "'Opening balance (stock before the ledger existed)' "
        "FROM products WHERE current_stock > 0"
    ))
    db.commit()

print("Migration finished.")
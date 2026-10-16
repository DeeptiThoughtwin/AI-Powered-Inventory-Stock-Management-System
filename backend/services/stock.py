"""Stock helpers used by many endpoints."""
from sqlalchemy import func

from models import Product, StockMovement


def record_movement(db, product_id, quantity_change, movement_type,
                    reason, reference_type=None, reference_id=None):
    """Write one row in the stock history. Called on every stock change.

    This only adds the row to the session. It does not update
    Product.current_stock and does not commit. The caller must change the
    stock and call this inside the same database transaction, so the history
    and the stock quantity either both save or both roll back.

    Args:
        db: SQLAlchemy session.
        product_id: ID of the product whose stock changed.
        quantity_change: Signed units changed (positive adds stock, negative
            removes it).
        movement_type: Kind of change, e.g. purchase, sale, adjustment.
        reason: Short explanation of why the stock changed.
        reference_type: Optional type of the source record (e.g. "sale").
        reference_id: Optional ID of the source record.
    """
    db.add(StockMovement(
        product_id=product_id,
        quantity_change=quantity_change,
        movement_type=movement_type,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=reason,
    ))


def low_stock_filter():
    """One definition of 'low stock', used everywhere.

    A product is low when current stock is at or below its minimum stock. A
    missing (NULL) minimum is treated as 0.

    Returns:
        A SQLAlchemy condition to pass into .filter(...). It does not
        filter by is_active, so callers add that themselves.
    """
    return Product.current_stock <= func.coalesce(Product.minimum_stock, 0)


def stock_consistency(db):
    """For every product, the history total must equal current_stock.

    Adds up all stock movements per product and compares the sum with the
    stored current_stock. Any difference means stock changed without being
    recorded (or history was edited). Includes inactive products. Read-only.

    Args:
        db: SQLAlchemy session.

    Returns:
        Dict with:
          products_checked: number of products compared.
          mismatch_count: number of products where the totals differ.
          mismatches: list of {product_id, name, current_stock, ledger_total}.
    """
    rows = (
        db.query(
            Product.id,
            Product.name,
            Product.current_stock,
            func.coalesce(func.sum(StockMovement.quantity_change), 0).label("ledger_total"),
        )
        .outerjoin(StockMovement, StockMovement.product_id == Product.id)
        .group_by(Product.id, Product.name, Product.current_stock)
        .all()
    )
    mismatches = [
        {
            "product_id": r.id,
            "name": r.name,
            "current_stock": r.current_stock,
            "ledger_total": int(r.ledger_total),
        }
        for r in rows
        if r.current_stock != int(r.ledger_total)
    ]
    return {
        "products_checked": len(rows),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
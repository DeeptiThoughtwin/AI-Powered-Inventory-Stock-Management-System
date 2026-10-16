"""Stock history, manual corrections and the stock-vs-history consistency check."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Product, StockMovement
from schemas.stock import StockAdjustment
from services.stock import record_movement, stock_consistency
from utils.validation import MAX_STOCK

router = APIRouter(tags=["Stock history"])


@router.get("/products/{product_id}/movements")
def get_product_movements(product_id: int, limit: int = 1000,
                          db: Session = Depends(get_db)):
    """Get the stock history of one product, newest first.

    Every stock change (purchase, sale, adjustment, return, opening stock) is
    one row here, so adding up all rows explains the product's current stock.
    Read-only.

    Args:
        product_id: ID of the product.
        limit: Maximum number of rows to return, clamped to 1-5000
            (default 1000).
        db: Database session, injected by FastAPI.

    Returns:
        List of StockMovement records (quantity_change, movement_type,
        reference, reason, timestamp), newest first.

    Raises:
        HTTPException: 404 if the product does not exist.
    """
    limit = max(1, min(limit, 5000))
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return (
        db.query(StockMovement)
        .filter(StockMovement.product_id == product_id)
        .order_by(StockMovement.id.desc())
        .limit(limit)
        .all()
    )


@router.get("/movements")
def get_all_movements(
    movement_type: str | None = None,
    product_id: int | None = None,
    limit: int = 1000,
    db: Session = Depends(get_db),
):
    """Get stock history across all products, with optional filters.

    Both filters are optional and can be combined. Read-only.

    Args:
        movement_type: Only rows of this type (e.g. "sale", "purchase",
            "adjustment"). An unknown type returns an empty list.
        product_id: Only rows for this product.
        limit: Maximum number of rows to return, clamped to 1-5000
            (default 1000).
        db: Database session, injected by FastAPI.

    Returns:
        List of StockMovement records, newest first.
    """
    limit = max(1, min(limit, 5000))
    query = db.query(StockMovement)
    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type)
    if product_id:
        query = query.filter(StockMovement.product_id == product_id)
    return query.order_by(StockMovement.id.desc()).limit(limit).all()


@router.post("/products/{product_id}/adjust-stock")
def adjust_stock(product_id: int, data: StockAdjustment, db: Session = Depends(get_db)):
    """Manually correct a product's stock and log the reason.

    Use this for damage, loss, recounts and similar corrections. The product
    row is locked while this runs, and the new quantity and the history entry
    are saved together in one transaction, so stock and history can't drift
    apart. Works on inactive products too.

    Args:
        product_id: ID of the product.
        data: quantity_change (positive adds stock, negative removes it) and
            the reason, from the request body.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with product_id and the new current_stock.

    Raises:
        HTTPException: 400 if quantity_change is 0 or the result would be
            below zero or above MAX_STOCK, 404 if the product does not exist,
            500 on unexpected errors (everything is rolled back).
    """
    if data.quantity_change == 0:
        raise HTTPException(status_code=400, detail="quantity_change cannot be 0")
    try:
        product = (
            db.query(Product).filter(Product.id == product_id).with_for_update().first()
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        new_stock = product.current_stock + data.quantity_change
        if new_stock < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Stock cannot go below zero. Available: {product.current_stock}"
            )
        if new_stock > MAX_STOCK:
            raise HTTPException(
                status_code=400,
                detail=f"Stock cannot exceed {MAX_STOCK:,} units"
            )

        product.current_stock = new_stock
        record_movement(db, product.id, data.quantity_change, "adjustment", data.reason)
        db.commit()
        return {"product_id": product.id, "current_stock": new_stock}

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not adjust stock")


@router.get("/analytics/stock-consistency")
def check_stock_consistency(db: Session = Depends(get_db)):
    """Check that every product's stock matches its movement history.

    Adds up all movements per product and compares the total with the stored
    current_stock. Any difference means stock changed without being recorded.
    Read-only.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        Dict with products_checked, mismatch_count and mismatches (each with
        product_id, name, current_stock and ledger_total).
    """
    return stock_consistency(db)
"""Low-stock alerts."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.analytics import low_stock_products

router = APIRouter(tags=["Alerts"])


@router.get("/alerts/low-stock")
def get_low_stock_products(db: Session = Depends(get_db)):
    """List active products whose stock is at or below their minimum level.

    Read-only. Uses the shared low-stock rule, so the result always matches
    the dashboard and the AI insights. Products are sorted with the lowest
    stock first.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        Dict with total_alerts (number of low-stock products) and products
        (the matching Product records).
    """
    products = low_stock_products(db)
    return {"total_alerts": len(products), "products": products}
"""Demand forecast, reorder recommendations and purchase orders."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Product, Supplier, PurchaseOrder
from schemas.purchase_order import PurchaseOrderCreate
from services.forecasting import forecast, reorder_recommendations

router = APIRouter(tags=["Forecast and reorder"])


@router.get("/analytics/forecast/{product_id}")
def forecast_demand(
    product_id: int,
    history_days: int = 30,
    window: int = 7,
    horizon_days: int = 7,
    db: Session = Depends(get_db),
):
    """Forecast a product's demand using a moving average.

    Read-only. The forecast is calculated in Python from recorded sales. The
    response includes the history used and the forecast for each past day, so
    the accuracy can be checked.

    Args:
        product_id: ID of the product to forecast.
        history_days: Days of past sales to use (7 to 365).
        window: Moving average size in days (2 up to history_days).
        horizon_days: Days ahead to predict (1 to 90).
        db: Database session, injected by FastAPI.

    Returns:
        Dict with predicted_daily_demand, predicted_total_demand,
        average_error_units_per_day, history and future.

    Raises:
        HTTPException: 400 if any parameter is out of range, 404 if the
            product does not exist.
    """
    return forecast(db, product_id, history_days, window, horizon_days)


@router.get("/reorder/recommendations")
def get_reorder_recommendations(window: int = 14, db: Session = Depends(get_db)):
    """Get suggested reorders for active products.

    Read-only. Nothing is ordered and no stock changes. Each suggestion is
    based on current stock, recent demand, supplier lead time and safety
    stock, and includes a plain-language explanation. The user reviews these
    and approves one by calling POST /purchase-orders.

    Args:
        window: Days of sales history used to estimate daily demand (2 to 90).
        db: Database session, injected by FastAPI.

    Returns:
        Dict with window_days, count and recommendations (largest
        recommended quantity first).

    Raises:
        HTTPException: 400 if window is outside 2 to 90.
    """
    return reorder_recommendations(db, window)


@router.post("/purchase-orders")
def create_purchase_order(order_data: PurchaseOrderCreate, db: Session = Depends(get_db)):
    """Create an approved purchase order. Calling this IS the user's approval.

    This only records the order. It never changes stock. Stock goes up later,
    when the delivery is recorded as a real purchase. The AI and the
    recommendations never call this endpoint, so no order is placed without
    a person choosing to.

    Args:
        order_data: Product, supplier and quantity from the request body.
        db: Database session, injected by FastAPI.

    Returns:
        The created PurchaseOrder record, with status "approved".

    Raises:
        HTTPException: 404 if the product or supplier does not exist, 400 if
            the product is deactivated.
    """
    product = db.query(Product).filter(Product.id == order_data.product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if not product.is_active:
        raise HTTPException(status_code=400, detail="Product is deactivated")
    supplier = db.query(Supplier).filter(Supplier.id == order_data.supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    order = PurchaseOrder(
        product_id=order_data.product_id,
        supplier_id=order_data.supplier_id,
        quantity=order_data.quantity,
        status="approved",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("/purchase-orders")
def get_purchase_orders(db: Session = Depends(get_db)):
    """List all purchase orders, newest first.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        List of PurchaseOrder records.
    """
    return db.query(PurchaseOrder).order_by(PurchaseOrder.id.desc()).all()
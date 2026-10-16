"""Demand forecast (moving average) and reorder recommendations."""
from datetime import date, timedelta
from math import ceil

from fastapi import HTTPException
from sqlalchemy import func, cast, Date

from models import Product, Supplier, Sale


def daily_units_sold(db, product_id, days):
    """Units sold per day for the last `days` days, oldest first (0 on quiet days).

    Args:
        db: SQLAlchemy session.
        product_id: ID of the product to look up.
        days: Number of days to cover, counting today as the last day.

    Returns:
        List of (date, units_sold) tuples, one per day, oldest first. Days with
        no sales are included with 0, so the list always has `days` entries.
    """
    first_day = date.today() - timedelta(days=days - 1)
    sale_day = cast(Sale.sale_date, Date)
    rows = (
        db.query(sale_day, func.sum(Sale.quantity))
        .filter(Sale.product_id == product_id, Sale.sale_date >= first_day)
        .group_by(sale_day)
        .all()
    )
    by_day = {row[0]: int(row[1]) for row in rows}
    series = []
    for i in range(days):
        day = first_day + timedelta(days=i)
        series.append((day, by_day.get(day, 0)))
    return series


def forecast(db, product_id, history_days=30, window=7, horizon_days=7):
    """Forecast a product's demand using a simple moving average.

    For each past day, the forecast is the average of the previous `window`
    days, which lets you compare predictions with what actually sold. The
    future forecast is a flat line: the average of the last `window` days,
    repeated for every day of the horizon.

    Args:
        db: SQLAlchemy session.
        product_id: ID of the product to forecast.
        history_days: How many past days of sales to use (7 to 365).
        window: Moving average size in days (2 up to history_days).
        horizon_days: How many days ahead to predict (1 to 90).

    Returns:
        Dict with product_id, name, window_days, predicted_daily_demand,
        predicted_total_demand, horizon_days, average_error_units_per_day
        (mean absolute error on past days, or None if there is not enough
        history), history (date, actual_units, forecast_units per day) and
        future (date, forecast_units per day).

    Raises:
        HTTPException: 400 if any parameter is out of range, 404 if the
            product does not exist.
    """
    if not 7 <= history_days <= 365:
        raise HTTPException(status_code=400, detail="history_days must be between 7 and 365")
    if not 2 <= window <= history_days:
        raise HTTPException(status_code=400, detail="window must be between 2 and history_days")
    if not 1 <= horizon_days <= 90:
        raise HTTPException(status_code=400, detail="horizon_days must be between 1 and 90")

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    series = daily_units_sold(db, product_id, history_days)
    units = [u for _, u in series]

    history = []
    for i, (day, actual) in enumerate(series):
        forecast_units = round(sum(units[i - window:i]) / window, 2) if i >= window else None
        history.append({
            "date": day.isoformat(),
            "actual_units": actual,
            "forecast_units": forecast_units,
        })

    daily_forecast = sum(units[-window:]) / window
    future = [
        {
            "date": (date.today() + timedelta(days=i + 1)).isoformat(),
            "forecast_units": round(daily_forecast, 2),
        }
        for i in range(horizon_days)
    ]

    compared = [h for h in history if h["forecast_units"] is not None]
    avg_error = (
        round(sum(abs(h["actual_units"] - h["forecast_units"]) for h in compared) / len(compared), 2)
        if compared else None
    )

    return {
        "product_id": product.id,
        "name": product.name,
        "window_days": window,
        "predicted_daily_demand": round(daily_forecast, 2),
        "predicted_total_demand": round(daily_forecast * horizon_days, 1),
        "horizon_days": horizon_days,
        "average_error_units_per_day": avg_error,
        "history": history,
        "future": future,
    }


def average_daily_demand(db, window):
    """Average units sold per day for every product over the last `window` days.

    Args:
        db: SQLAlchemy session.
        window: Number of days to average over, counting today.

    Returns:
        Dict of {product_id: average units per day}. Products with no sales in
        the window are not in the dict, so callers should default to 0.
    """
    first_day = date.today() - timedelta(days=window - 1)
    rows = (
        db.query(Sale.product_id, func.sum(Sale.quantity))
        .filter(Sale.sale_date >= first_day)
        .group_by(Sale.product_id)
        .all()
    )
    return {pid: int(total) / window for pid, total in rows}


def reorder_recommendations(db, window=14):
    """Recommend which active products to reorder, and how many units.

    Recommendation only. Nothing is ordered and no stock changes here.

    For each product, the target stock is:
        (average daily demand x supplier lead time) + safety stock
    and the recommended quantity is the target minus current stock. Products
    that are already covered are skipped. If the product has no supplier, a
    7-day lead time is assumed and `needs_supplier` is set. If the product has
    no minimum stock set, a safety stock of 5 is used.

    Args:
        db: SQLAlchemy session.
        window: Days of sales history used to estimate daily demand (2 to 90).

    Returns:
        Dict with window_days, count and recommendations, a list sorted by
        recommended_quantity (largest first). Each item has product details,
        current_stock, avg_daily_demand, lead_time_days, safety_stock,
        supplier info, recommended_quantity, urgency ("high" or "medium") and
        a plain-language explanation.

    Raises:
        HTTPException: 400 if window is outside 2 to 90.
    """
    if not 2 <= window <= 90:
        raise HTTPException(status_code=400, detail="window must be between 2 and 90")

    demand = average_daily_demand(db, window)
    suppliers = {s.id: s for s in db.query(Supplier).all()}
    products = db.query(Product).filter(Product.is_active.is_(True)).all()

    recommendations = []
    for p in products:
        supplier = suppliers.get(p.supplier_id)
        lead_time = supplier.lead_time_days if supplier else 7
        daily = demand.get(p.id, 0)
        safety_stock = p.minimum_stock if p.minimum_stock else 5  # fallback safety stock

        needed = (daily * lead_time) + safety_stock
        quantity = ceil(needed - p.current_stock)

        # An out-of-stock product always gets at least safety stock + lead-time demand.
        if p.current_stock == 0:
            quantity = max(quantity, safety_stock + ceil(daily * lead_time))

        if quantity <= 0:
            continue

        urgency_label = "high" if p.current_stock == 0 or p.current_stock <= safety_stock else "medium"

        recommendations.append({
            "product_id": p.id,
            "name": p.name,
            "sku": p.sku,
            "current_stock": p.current_stock,
            "avg_daily_demand": round(daily, 2),
            "lead_time_days": lead_time,
            "safety_stock": safety_stock,
            "supplier_id": p.supplier_id,
            "supplier_name": supplier.name if supplier else None,
            "needs_supplier": supplier is None,
            "recommended_quantity": quantity,
            "urgency": urgency_label,
            "explanation": (
                f"Expected demand over {lead_time} days of lead time is "
                f"{daily * lead_time:.1f} units, plus {safety_stock} safety stock, "
                f"minus {p.current_stock} in stock."
            ),
        })

    recommendations.sort(key=lambda r: r["recommended_quantity"], reverse=True)
    return {
        "window_days": window,
        "count": len(recommendations),
        "recommendations": recommendations,
    }
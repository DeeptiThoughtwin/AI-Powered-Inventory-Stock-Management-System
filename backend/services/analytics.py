"""Read-only calculations for dashboards, reports and the AI. Nothing here changes data."""
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, cast, Date, and_

from models import Product, Sale
from services.stock import low_stock_filter, stock_consistency


def check_date_range(start_date, end_date):
    """Validate that a date range is not reversed.

    Args:
        start_date: Optional start of the range (date or None).
        end_date: Optional end of the range (date or None).

    Raises:
        HTTPException: 400 if both dates are given and start_date is after end_date.
    """
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")


def sale_date_conditions(start_date, end_date):
    """Build SQLAlchemy filter conditions for a sale date range.

    The end date is inclusive: the condition uses "< end_date + 1 day" so sales
    made at any time on end_date are counted.

    Args:
        start_date: Optional first day to include.
        end_date: Optional last day to include.

    Returns:
        A list of SQLAlchemy conditions (empty if no dates are given), meant to
        be unpacked into .filter(*conditions) or and_(...).
    """
    conditions = []
    if start_date:
        conditions.append(Sale.sale_date >= start_date)
    if end_date:
        conditions.append(Sale.sale_date < end_date + timedelta(days=1))
    return conditions


def low_stock_products(db):
    """Return active products at or below their minimum stock threshold.

    Args:
        db: SQLAlchemy session.

    Returns:
        List of Product objects, lowest stock first.
    """
    return (
        db.query(Product)
        .filter(Product.is_active.is_(True), low_stock_filter())
        .order_by(Product.current_stock.asc())
        .all()
    )


def inventory_summary(db):
    """Summarise current inventory across all products.

    Note: total_products, total_units_in_stock and both value figures include
    inactive products; only low_stock_count is limited to active products.

    Args:
        db: SQLAlchemy session.

    Returns:
        Dict with total_products, total_units_in_stock, inventory_cost_value
        (stock x purchase price), inventory_retail_value (stock x selling price)
        and low_stock_count.
    """
    total_products = db.query(Product).count()
    total_units = db.query(func.coalesce(func.sum(Product.current_stock), 0)).scalar()
    cost_value = db.query(
        func.coalesce(func.sum(Product.current_stock * Product.purchase_price), 0)
    ).scalar()
    retail_value = db.query(
        func.coalesce(func.sum(Product.current_stock * Product.selling_price), 0)
    ).scalar()
    low_stock_count = (
        db.query(Product)
        .filter(Product.is_active.is_(True), low_stock_filter())
        .count()
    )
    return {
        "total_products": total_products,
        "total_units_in_stock": int(total_units),
        "inventory_cost_value": round(float(cost_value), 2),
        "inventory_retail_value": round(float(retail_value), 2),
        "low_stock_count": low_stock_count,
    }


def sales_summary(db, start_date=None, end_date=None, product_id=None, category=None):
    """Calculate total sales figures for a period, optionally filtered.

    Args:
        db: SQLAlchemy session.
        start_date: Optional first day to include.
        end_date: Optional last day to include.
        product_id: Optional product ID to filter by.
        category: Optional product category to filter by.

    Returns:
        Dict with total_sales_amount, total_units_sold and total_transactions.

    Raises:
        HTTPException: 400 if start_date is after end_date.
    """
    check_date_range(start_date, end_date)
    query = (
        db.query(
            func.coalesce(func.sum(Sale.total_amount), 0),
            func.coalesce(func.sum(Sale.quantity), 0),
            func.count(Sale.id),
        )
        .select_from(Sale)
        .join(Product, Product.id == Sale.product_id)
        .filter(*sale_date_conditions(start_date, end_date))
    )
    if product_id:
        query = query.filter(Sale.product_id == product_id)
    if category:
        query = query.filter(Product.category == category)

    amount, units, transactions = query.one()
    return {
        "total_sales_amount": round(float(amount), 2),
        "total_units_sold": int(units),
        "total_transactions": transactions,
    }


def sales_trend(db, start_date=None, end_date=None, product_id=None, category=None):
    """Return daily sales totals for charting a trend over time.

    Days with no sales are not included in the result.

    Args:
        db: SQLAlchemy session.
        start_date: Optional first day to include.
        end_date: Optional last day to include.
        product_id: Optional product ID to filter by.
        category: Optional product category to filter by.

    Returns:
        List of dicts ordered by date, each with date (ISO string),
        sales_amount, units_sold and transactions.

    Raises:
        HTTPException: 400 if start_date is after end_date.
    """
    check_date_range(start_date, end_date)
    sale_day = cast(Sale.sale_date, Date)
    query = (
        db.query(
            sale_day.label("day"),
            func.sum(Sale.total_amount).label("sales_amount"),
            func.sum(Sale.quantity).label("units_sold"),
            func.count(Sale.id).label("transactions"),
        )
        .select_from(Sale)
        .join(Product, Product.id == Sale.product_id)
        .filter(*sale_date_conditions(start_date, end_date))
    )
    if product_id:
        query = query.filter(Sale.product_id == product_id)
    if category:
        query = query.filter(Product.category == category)

    rows = query.group_by(sale_day).order_by(sale_day).all()
    return [
        {
            "date": row.day.isoformat(),
            "sales_amount": round(float(row.sales_amount), 2),
            "units_sold": int(row.units_sold),
            "transactions": row.transactions,
        }
        for row in rows
    ]


def best_selling(db, limit=5, start_date=None, end_date=None, product_id=None, category=None):
    """Rank products by units sold, highest first.

    Only products with at least one sale in the period appear. Ties on units
    are broken by revenue.

    Args:
        db: SQLAlchemy session.
        limit: Maximum number of products to return (default 5).
        start_date: Optional first day to include.
        end_date: Optional last day to include.
        product_id: Optional product ID to filter by.
        category: Optional product category to filter by.

    Returns:
        List of dicts with product_id, name, sku, units_sold and revenue.

    Raises:
        HTTPException: 400 if start_date is after end_date.
    """
    check_date_range(start_date, end_date)
    query = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            func.sum(Sale.quantity).label("units_sold"),
            func.sum(Sale.total_amount).label("revenue"),
        )
        .join(Sale, Sale.product_id == Product.id)
        .filter(*sale_date_conditions(start_date, end_date))
    )
    if product_id:
        query = query.filter(Product.id == product_id)
    if category:
        query = query.filter(Product.category == category)

    rows = (
        query.group_by(Product.id, Product.name, Product.sku)
        .order_by(func.sum(Sale.quantity).desc(), func.sum(Sale.total_amount).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "product_id": r.id,
            "name": r.name,
            "sku": r.sku,
            "units_sold": int(r.units_sold),
            "revenue": round(float(r.revenue), 2),
        }
        for r in rows
    ]


def slow_moving(db, limit=5, start_date=None, end_date=None, product_id=None, category=None):
    """Rank active products by fewest units sold, lowest first.

    Products with no sales in the period are included with 0 units. Ties are
    broken by higher current stock first, so overstocked items surface sooner.

    Args:
        db: SQLAlchemy session.
        limit: Maximum number of products to return (default 5).
        start_date: Optional first day to include.
        end_date: Optional last day to include.
        product_id: Optional product ID to filter by.
        category: Optional product category to filter by.

    Returns:
        List of dicts with product_id, name, sku, current_stock, units_sold
        and revenue.

    Raises:
        HTTPException: 400 if start_date is after end_date.
    """
    check_date_range(start_date, end_date)
    units_sold = func.coalesce(func.sum(Sale.quantity), 0)
    revenue = func.coalesce(func.sum(Sale.total_amount), 0)

    # The date filter sits inside the join so products with no sales in the
    # period still show up with 0 instead of disappearing.
    query = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.current_stock,
            units_sold.label("units_sold"),
            revenue.label("revenue"),
        )
        .outerjoin(
            Sale,
            and_(Sale.product_id == Product.id, *sale_date_conditions(start_date, end_date)),
        )
        .filter(Product.is_active.is_(True))
    )
    if product_id:
        query = query.filter(Product.id == product_id)
    if category:
        query = query.filter(Product.category == category)

    rows = (
        query.group_by(Product.id, Product.name, Product.sku, Product.current_stock)
        .order_by(units_sold.asc(), Product.current_stock.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "product_id": r.id,
            "name": r.name,
            "sku": r.sku,
            "current_stock": r.current_stock,
            "units_sold": int(r.units_sold),
            "revenue": round(float(r.revenue), 2),
        }
        for r in rows
    ]


def anomalies(db):
    """Detect unusual sales patterns and stock records that don't add up.

    Compares the daily sales rate of the last 7 days against the 21 days
    before that, per product:
      - demand_spike: at least 5 units sold recently and the recent daily
        rate is more than double the earlier rate.
      - sales_drop: at least 5 units sold in the earlier period and the
        recent daily rate is less than half the earlier rate.

    Args:
        db: SQLAlchemy session.

    Returns:
        Dict with:
          sales_anomalies: list of findings (product_id, name, type,
              recent_units_per_day, previous_units_per_day, message).
          stock_discrepancies: products whose current stock does not match
              their movement history, from services.stock.stock_consistency.
    """
    today = date.today()
    recent_start = today - timedelta(days=6)   # last 7 days
    prior_start = today - timedelta(days=27)   # the 21 days before that

    def units_by_product(*conditions):
        """Return {product_id: total units sold} for sales matching the conditions."""
        rows = (
            db.query(Sale.product_id, func.sum(Sale.quantity))
            .filter(*conditions).group_by(Sale.product_id).all()
        )
        return {pid: int(total) for pid, total in rows}

    recent = units_by_product(Sale.sale_date >= recent_start)
    prior = units_by_product(Sale.sale_date >= prior_start, Sale.sale_date < recent_start)
    names = {p.id: p.name for p in db.query(Product).all()}

    findings = []
    for pid in set(recent) | set(prior):
        r_units, p_units = recent.get(pid, 0), prior.get(pid, 0)
        r_rate, p_rate = r_units / 7, p_units / 21
        if r_units >= 5 and r_rate > 2 * p_rate:
            kind = "demand_spike"
            message = "Sales in the last 7 days are more than double the previous 3 weeks."
        elif p_units >= 5 and r_rate < 0.5 * p_rate:
            kind = "sales_drop"
            message = "Sales in the last 7 days are less than half the previous 3 weeks."
        else:
            continue
        findings.append({
            "product_id": pid, "name": names.get(pid, str(pid)), "type": kind,
            "recent_units_per_day": round(r_rate, 2),
            "previous_units_per_day": round(p_rate, 2),
            "message": message,
        })

    return {"sales_anomalies": findings,
            "stock_discrepancies": stock_consistency(db)}
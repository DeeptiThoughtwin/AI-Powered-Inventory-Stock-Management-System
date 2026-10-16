"""Sales analytics for the dashboard. These endpoints only read data."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services import analytics

router = APIRouter(tags=["Analytics"])


@router.get("/analytics/summary")
def get_analytics_summary(db: Session = Depends(get_db)):
    """Get the current inventory snapshot.

    Returns total products, units in stock, stock value at cost and at
    selling price, and the number of low-stock products. Calculated live
    from the products table, never stored.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        Dict with total_products, total_units_in_stock, inventory_cost_value,
        inventory_retail_value and low_stock_count.
    """
    return analytics.inventory_summary(db)


@router.get("/analytics/sales-summary")
def get_sales_summary(
    start_date: date | None = None,
    end_date: date | None = None,
    product_id: int | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    """Get total sales figures, optionally filtered.

    All filters are optional and can be combined. With no filters, the
    summary covers all recorded sales. The end date is inclusive.

    Args:
        start_date: First day to include (YYYY-MM-DD).
        end_date: Last day to include (YYYY-MM-DD).
        product_id: Only count sales of this product.
        category: Only count sales of products in this category.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with total_sales_amount, total_units_sold and total_transactions.

    Raises:
        HTTPException: 400 if start_date is after end_date.
    """
    return analytics.sales_summary(db, start_date, end_date, product_id, category)


@router.get("/analytics/sales-trend")
def get_sales_trend(
    start_date: date | None = None,
    end_date: date | None = None,
    product_id: int | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    """Get daily sales totals for drawing a trend chart.

    Days with no sales are not included, so the chart should fill gaps with
    zero if it needs a continuous line.

    Args:
        start_date: First day to include (YYYY-MM-DD).
        end_date: Last day to include (YYYY-MM-DD).
        product_id: Only count sales of this product.
        category: Only count sales of products in this category.
        db: Database session, injected by FastAPI.

    Returns:
        List ordered by date, each item with date, sales_amount, units_sold
        and transactions.

    Raises:
        HTTPException: 400 if start_date is after end_date.
    """
    return analytics.sales_trend(db, start_date, end_date, product_id, category)


@router.get("/analytics/best-selling")
def get_best_selling_products(
    limit: int = 5,
    start_date: date | None = None,
    end_date: date | None = None,
    product_id: int | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    """Get the top-selling products by units sold.

    Only products with at least one sale in the period are listed. Ties are
    broken by revenue.

    Args:
        limit: Maximum number of products to return (default 5).
        start_date: First day to include (YYYY-MM-DD).
        end_date: Last day to include (YYYY-MM-DD).
        product_id: Only consider this product.
        category: Only consider products in this category.
        db: Database session, injected by FastAPI.

    Returns:
        List of dicts with product_id, name, sku, units_sold and revenue,
        highest sellers first.

    Raises:
        HTTPException: 400 if start_date is after end_date.
    """
    return analytics.best_selling(db, limit, start_date, end_date, product_id, category)


@router.get("/analytics/slow-moving")
def get_slow_moving_products(
    limit: int = 5,
    start_date: date | None = None,
    end_date: date | None = None,
    product_id: int | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    """Get the slowest-selling active products.

    Products with no sales in the period are included with 0 units. Ties are
    broken by higher current stock first, so overstocked items appear sooner.

    Args:
        limit: Maximum number of products to return (default 5).
        start_date: First day to include (YYYY-MM-DD).
        end_date: Last day to include (YYYY-MM-DD).
        product_id: Only consider this product.
        category: Only consider products in this category.
        db: Database session, injected by FastAPI.

    Returns:
        List of dicts with product_id, name, sku, current_stock, units_sold
        and revenue, slowest first.

    Raises:
        HTTPException: 400 if start_date is after end_date.
    """
    return analytics.slow_moving(db, limit, start_date, end_date, product_id, category)


@router.get("/analytics/anomalies")
def get_anomalies(db: Session = Depends(get_db)):
    """Detect unusual sales activity and stock records that don't add up.

    Compares each product's sales over the last 7 days with the 21 days
    before that to flag demand spikes and sales drops. Also runs the stock
    audit, which checks that each product's movement history adds up to its
    current stock. Takes no filters: the time windows are fixed.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        Dict with sales_anomalies (list of spike/drop findings) and
        stock_discrepancies (products checked, mismatch count, mismatches).
    """
    return analytics.anomalies(db)
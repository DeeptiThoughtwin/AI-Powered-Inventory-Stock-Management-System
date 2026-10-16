"""Collects the calculated numbers and builds the rule-based summary (no AI needed)."""
from services import analytics
from services.forecasting import reorder_recommendations


def build_metrics(db):
    """Collect every number the insights page and the AI report are based on.

    This is the single source of truth for insights: both the rule-based
    summary and the AI prompt read from this dict, so the AI never sees
    anything that wasn't calculated from the database. Read-only.

    Args:
        db: SQLAlchemy session.

    Returns:
        Dict with:
          inventory: totals and stock values (all time).
          sales: total sales, units and transactions (all time).
          best_selling: top 3 products by units sold.
          slow_moving: 3 slowest active products.
          low_stock: list of {name, current_stock, minimum_stock}.
          reorder: top 5 reorder recommendations (14-day demand window).
          anomalies: sales spikes/drops and stock discrepancies.
    """
    low = analytics.low_stock_products(db)
    return {
        "inventory": analytics.inventory_summary(db),
        "sales": analytics.sales_summary(db),
        "best_selling": analytics.best_selling(db, limit=3),
        "slow_moving": analytics.slow_moving(db, limit=3),
        "low_stock": [{"name": p.name, "current_stock": p.current_stock,
                       "minimum_stock": p.minimum_stock} for p in low],
        "reorder": reorder_recommendations(db, window=14)["recommendations"][:5],
        "anomalies": analytics.anomalies(db),
    }


def rule_based_insights(db):
    """Turn the calculated metrics into plain sentences (free and instant).

    Every sentence is built from numbers returned by build_metrics, with no AI
    call, so it works offline and cannot invent figures. Each insight carries
    a `basis` field holding the raw data behind the sentence.

    Args:
        db: SQLAlchemy session.

    Returns:
        Dict with:
          generated_from: a label saying only calculated metrics were used.
          insights: list of {title, text, basis} covering sales, best sellers,
              slow movers, low stock, reordering and unusual activity.
    """
    m = build_metrics(db)
    s = m["sales"]
    items = []

    if s["total_transactions"] == 0:
        items.append({"title": "Sales", "text": "No sales have been recorded yet.", "basis": s})
    else:
        items.append({"title": "Sales", "basis": s, "text": (
            f"{s['total_units_sold']} units sold across {s['total_transactions']} transactions, "
            f"totaling ₹{s['total_sales_amount']:,.2f}.")})

    if m["best_selling"]:
        names = ", ".join(f"{b['name']} ({b['units_sold']} units)" for b in m["best_selling"])
        items.append({"title": "Selling well", "text": f"Top moving items: {names}.",
                      "basis": m["best_selling"]})

    if m["slow_moving"]:
        names = ", ".join(f"{x['name']} ({x['units_sold']} sold, {x['current_stock']} in stock)"
                          for x in m["slow_moving"])
        items.append({"title": "Selling slowly", "text": f"Slow movers blocking capital: {names}.",
                      "basis": m["slow_moving"]})

    if not m["low_stock"]:
        items.append({"title": "Low stock", "basis": [],
                      "text": "All items are comfortably above minimum stock levels."})
    else:
        names = ", ".join(f"{p['name']} ({p['current_stock']} left)" for p in m["low_stock"])
        items.append({"title": "Low stock", "basis": m["low_stock"],
                      "text": f"{len(m['low_stock'])} product(s) running low: {names}."})

    if not m["reorder"]:
        items.append({"title": "Reordering", "basis": [],
                      "text": "No urgent reorders needed based on current sales speed."})
    else:
        names = ", ".join(f"{r['name']}: ~{r['recommended_quantity']} units"
                          for r in m["reorder"][:3])
        items.append({"title": "Reordering", "basis": m["reorder"][:3],
                      "text": f"Recommended reorders to maintain stock: {names}."})

    anomalies = m["anomalies"]
    if anomalies["sales_anomalies"]:
        text = " ".join(f"{a['name']}: {a['message']}" for a in anomalies["sales_anomalies"])
    else:
        text = "No unusual sales spikes or drops detected."
    if anomalies["stock_discrepancies"]["mismatch_count"] > 0:
        names = ", ".join(x["name"] for x in anomalies["stock_discrepancies"]["mismatches"])
        text += f" Stock audit mismatch found for: {names}."
    items.append({"title": "Unusual activity", "text": text, "basis": anomalies})

    return {"generated_from": "calculated metrics only", "insights": items}
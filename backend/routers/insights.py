"""Insights: a rule-based summary (no AI) and AI-written explanations of calculated numbers."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Product
from services.ai import ask_ai
from services.forecasting import forecast
from services.insights import build_metrics, rule_based_insights

router = APIRouter(tags=["Insights and AI"])


@router.get("/insights")
def get_insights(db: Session = Depends(get_db)):
    """Get a plain-language inventory summary without using AI.

    Every sentence is built from calculated metrics, so it is free, instant
    and cannot contain invented numbers. Read-only.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        Dict with generated_from and insights (a list of {title, text, basis}
        covering sales, best sellers, slow movers, low stock, reordering and
        unusual activity).
    """
    return rule_based_insights(db)


@router.post("/insights/ai")
def get_ai_insights(db: Session = Depends(get_db)):
    """Generate an AI-written performance report from calculated metrics.

    The metrics are calculated in the backend and passed to the AI, which
    only writes the explanation. It cannot change stock or place orders. The
    prompt asks for plain text with uppercase section headers and no
    markdown, so it displays cleanly as a printed-style report.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        Dict with summary (the AI text) and metrics (the exact numbers the AI
        was given, so the report can be checked against real data).
    """
    metrics = build_metrics(db)
    summary = ask_ai(
        "Provide a formal shop performance report for an Indian merchant. "
        "STRICT FORMATTING RULES: Do NOT use markdown symbols like ###, **, or bullet points (- or *). "
        "Instead, use clean uppercase section headers (e.g., SALES OVERVIEW), proper line spacing, "
        "and clean text lines so it looks like a professional printed business document.",
        metrics,
    )
    return {"summary": summary, "metrics": metrics}


@router.post("/analytics/forecast/{product_id}/explain")
def explain_forecast(product_id: int, history_days: int = 30, window: int = 7,
                     horizon_days: int = 7, db: Session = Depends(get_db)):
    """Forecast a product's demand and have the AI explain it in simple words.

    The forecast itself is a moving average calculated in Python. The AI only
    receives the finished numbers (predicted demand, accuracy, current stock
    and the last 14 days of actual vs forecast) and explains them. It does
    not create the forecast.

    Args:
        product_id: ID of the product to forecast.
        history_days: Days of past sales to use (7 to 365).
        window: Moving average size in days (2 up to history_days).
        horizon_days: Days ahead to predict (1 to 90).
        db: Database session, injected by FastAPI.

    Returns:
        Dict with forecast (the full forecast data) and explanation (the AI
        text).

    Raises:
        HTTPException: 400 if any parameter is out of range, 404 if the
            product does not exist.
    """
    f = forecast(db, product_id, history_days, window, horizon_days)
    product = db.query(Product).filter(Product.id == product_id).first()

    data = {k: f[k] for k in ("name", "window_days", "predicted_daily_demand",
                              "predicted_total_demand", "horizon_days",
                              "average_error_units_per_day")}
    data["history_days_used"] = history_days
    data["current_stock"] = product.current_stock
    data["recent_actual_vs_forecast"] = f["history"][-14:]

    explanation = ask_ai(
        "Explain this demand forecast simply to a shop owner in India: what demand is "
        "expected over the coming days, how it was calculated (moving average of recent "
        "sales), how accurate it was recently, and whether they need to restock soon. "
        "STRICT FORMATTING RULES: Do NOT use markdown symbols like ###, **, or bullet dashes (-). "
        "Use clean uppercase section titles (e.g., DEMAND OUTLOOK, RESTOCK RECOMMENDATION) "
        "and clear line breaks so it reads like a structured formal report.",
        data,
    )
    return {"forecast": f, "explanation": explanation}
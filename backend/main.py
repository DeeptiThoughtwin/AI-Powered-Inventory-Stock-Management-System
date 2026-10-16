"""Entry point. Creates the app, loads settings, and plugs in one router per module.
Run from the backend folder:   uvicorn main:app --reload --port 8001
"""
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Load the .env file FIRST (project root and backend folder) so keys are ready
# before the routers (and database.py) are imported below.
try:
    from dotenv import load_dotenv

    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR.parent / ".env")
except ImportError:
    pass

from database import get_db
from routers import (
    products, suppliers, purchases, sales, stock,
    alerts, analytics, reorder, insights,
)

app = FastAPI(title="Inventory Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "Inventory Management API is running"}


@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    return {"message": "Database session created successfully"}


app.include_router(products.router)
app.include_router(suppliers.router)
app.include_router(purchases.router)
app.include_router(sales.router)
app.include_router(stock.router)
app.include_router(alerts.router)
app.include_router(analytics.router)
app.include_router(reorder.router)
app.include_router(insights.router)

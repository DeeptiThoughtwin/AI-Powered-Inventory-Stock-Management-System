"""Small helpers and limits shared by the whole backend (no database access here)."""
import re
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

MAX_PRICE = Decimal("99999999.99")     # price columns are NUMERIC(10,2)
MAX_TOTAL = Decimal("9999999999.99")   # purchase/sale totals are NUMERIC(12,2)
MAX_QTY = 1_000_000                    # largest quantity in one transaction line
MAX_STOCK = 10_000_000                 # largest stock a product can hold

SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9 ()-]+$")


def clean_text(value):
    """Trim spaces. Empty text becomes None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def require_text(value, label):
    value = clean_text(value)
    if value is None:
        raise ValueError(f"{label} cannot be empty")
    return value


def check_money(value, label):
    """Allow at most 2 decimal places."""
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{label} must be a number")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError(f"{label} can have at most 2 decimal places")
    return value


def calc_total(quantity, unit_amount):
    """Exact money maths (no float rounding errors). Returns a Decimal."""
    total = (Decimal(str(unit_amount)) * quantity).quantize(Decimal("0.01"))
    if total > MAX_TOTAL:
        raise HTTPException(status_code=400, detail="Total amount is too large")
    return total

"""Request shapes for purchases (single and many products)."""
from pydantic import BaseModel, Field, field_validator

from utils.validation import MAX_PRICE, MAX_QTY, check_money


class PurchaseCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=MAX_QTY)
    unit_cost: float = Field(gt=0, le=float(MAX_PRICE))

    @field_validator("unit_cost")
    @classmethod
    def two_decimals(cls, v):
        return check_money(v, "Unit cost")


class PurchaseLine(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=MAX_QTY)
    unit_cost: float = Field(gt=0, le=float(MAX_PRICE))

    @field_validator("unit_cost")
    @classmethod
    def two_decimals(cls, v):
        return check_money(v, "Unit cost")


class PurchaseBulkCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    items: list[PurchaseLine] = Field(min_length=1, max_length=50)

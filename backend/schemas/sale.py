"""Request shapes for sales (single and many products)."""
from pydantic import BaseModel, Field, field_validator

from utils.validation import MAX_PRICE, MAX_QTY, check_money


class SaleCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=MAX_QTY)
    unit_price: float = Field(gt=0, le=float(MAX_PRICE))

    @field_validator("unit_price")
    @classmethod
    def two_decimals(cls, v):
        return check_money(v, "Unit price")


class SaleLine(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=MAX_QTY)
    unit_price: float = Field(gt=0, le=float(MAX_PRICE))

    @field_validator("unit_price")
    @classmethod
    def two_decimals(cls, v):
        return check_money(v, "Unit price")


class SaleBulkCreate(BaseModel):
    items: list[SaleLine] = Field(min_length=1, max_length=50)

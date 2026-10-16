"""Request shapes for products. Pydantic checks and cleans the data before any endpoint runs."""
from pydantic import BaseModel, Field, field_validator

from utils.validation import (
    MAX_PRICE, MAX_STOCK, SKU_PATTERN, clean_text, require_text, check_money,
)


class ProductCreate(BaseModel):
    name: str = Field(max_length=100)
    sku: str = Field(max_length=50)
    category: str | None = Field(default=None, max_length=100)
    purchase_price: float = Field(gt=0, le=float(MAX_PRICE))
    selling_price: float = Field(gt=0, le=float(MAX_PRICE))
    current_stock: int = Field(default=0, ge=0, le=MAX_STOCK)
    minimum_stock: int = Field(default=5, ge=0, le=MAX_STOCK)
    supplier_id: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        return require_text(v, "Name")

    @field_validator("sku")
    @classmethod
    def clean_sku(cls, v):
        v = require_text(v, "SKU").upper()
        if not SKU_PATTERN.match(v):
            raise ValueError("SKU can contain only letters, numbers, dot, dash and underscore")
        return v

    @field_validator("category")
    @classmethod
    def clean_category(cls, v):
        return clean_text(v)

    @field_validator("purchase_price", "selling_price")
    @classmethod
    def two_decimals(cls, v):
        return check_money(v, "Price")


class ProductUpdate(ProductCreate):
    """Same rules as ProductCreate. Stock can be edited from the product form."""


class ProductSupplierUpdate(BaseModel):
    supplier_id: int | None = Field(default=None, gt=0)  # send null to remove the supplier

"""Request shape for purchase orders."""
from pydantic import BaseModel, Field

from utils.validation import MAX_QTY


class PurchaseOrderCreate(BaseModel):
    product_id: int = Field(gt=0)
    supplier_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=MAX_QTY)

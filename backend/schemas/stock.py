"""Request shape for manual stock corrections."""
from pydantic import BaseModel, Field, field_validator

from utils.validation import MAX_STOCK, require_text


class StockAdjustment(BaseModel):
    quantity_change: int = Field(ge=-MAX_STOCK, le=MAX_STOCK)
    reason: str = Field(max_length=250)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, v):
        v = require_text(v, "Reason")
        if len(v) < 3:
            raise ValueError("Reason must be at least 3 characters")
        return v

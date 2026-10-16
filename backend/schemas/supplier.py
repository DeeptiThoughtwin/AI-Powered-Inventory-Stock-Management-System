"""Request shape for suppliers."""
import re

from pydantic import BaseModel, Field, field_validator

from utils.validation import EMAIL_PATTERN, PHONE_PATTERN, clean_text, require_text


class SupplierCreate(BaseModel):
    name: str = Field(max_length=100)
    contact_person: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=250)
    lead_time_days: int = Field(default=7, ge=0, le=365)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        return require_text(v, "Company name")

    @field_validator("contact_person", "address")
    @classmethod
    def clean_optional(cls, v):
        return clean_text(v)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v):
        v = clean_text(v)
        if v is None:
            return None
        v = v.lower()
        if not EMAIL_PATTERN.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v):
        v = clean_text(v)
        if v is None:
            return None
        digits = re.sub(r"\D", "", v)
        if not PHONE_PATTERN.match(v) or not 7 <= len(digits) <= 15:
            raise ValueError(
                "Phone must have 7 to 15 digits and may contain only digits, spaces, +, - and ( )"
            )
        return v

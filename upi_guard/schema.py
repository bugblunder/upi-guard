"""One validated transaction contract for API, CSV and simulator."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    transaction_id: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    timestamp: datetime
    payer_id: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    payee_id: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    device_id: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    amount: Decimal = Field(gt=0, le=1_000_000, max_digits=12, decimal_places=2)
    category: Literal["transfer", "grocery", "shopping", "bills", "travel", "food", "other"]
    channel: Literal["push", "qr", "collect"]
    # Deprecated hints retained for v2 CSV compatibility. Never used for scoring.
    account_age_days: int = Field(default=0, ge=0, le=36500)
    failed_attempts_1h: int = Field(default=0, ge=0, le=1000)

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone, for example +05:30 or Z")
        value = value.astimezone(timezone.utc)
        if value.year < 2020 or value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("timestamp must be between 2020 and server time plus five minutes")
        return value

    def payload(self):
        return self.model_dump(mode="json")


def calendar_age(dob, at):
    """Compatibility utility; DOB is deliberately absent from the v2 contract."""
    if dob > at:
        raise ValueError("birth date cannot be after transaction date")
    return at.year - dob.year - ((at.month, at.day) < (dob.month, dob.day))

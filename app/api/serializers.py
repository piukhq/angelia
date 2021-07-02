from typing import Optional

from pydantic import BaseModel


class ErrorSerializer(BaseModel):
    error_code: str
    error_message: str


class LoyaltyCardsAddsSerializer(BaseModel):
    id: int
    loyalty_plan: int
    errors: Optional[list[ErrorSerializer]] = None


class PaymentCardSerializer(BaseModel):
    id: int
    status: str
    name_on_card: str
    # card_nickname: str
    issuer: str
    expiry_month: str
    expiry_year: str


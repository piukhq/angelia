from pydantic import BaseModel


class LoyaltyCardSerializer(BaseModel):
    id: int


class PaymentCardSerializer(BaseModel):
    id: int
    status: str
    name_on_card: str
    card_nickname: str
    issuer: str
    expiry_month: str
    expiry_year: str

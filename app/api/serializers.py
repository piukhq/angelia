from typing import List, Optional

from pydantic import BaseModel, Extra


class LoyaltyCardSerializer(BaseModel):
    id: int


class PaymentCardSerializer(BaseModel, extra=Extra.forbid):
    id: int
    status: str
    name_on_card: str
    card_nickname: str
    issuer: str
    expiry_month: str
    expiry_year: str


class AlternativeCredentialSerializer(BaseModel, extra=Extra.forbid):
    order: int
    display_label: str
    validation: str
    description: str
    credential_slug: str
    type: str
    is_sensitive: bool
    choice: Optional[List[str]]


class CredentialSerializer(BaseModel, extra=Extra.forbid):
    order: int
    display_label: str
    validation: str
    description: str
    credential_slug: str
    type: str
    is_sensitive: bool
    choice: Optional[List[str]]
    alternative: Optional[AlternativeCredentialSerializer]


class DocumentSerializer(BaseModel, extra=Extra.forbid):
    name: str
    url: str
    description: str


class ConsentSerializer(BaseModel, extra=Extra.forbid):
    order: int
    consent_slug: str
    is_acceptance_required: bool
    description: str


class JourneyFieldsByClassSerializer(BaseModel, extra=Extra.forbid):
    credentials: List[CredentialSerializer]
    plan_documents: Optional[List[DocumentSerializer]]
    consents: Optional[List[ConsentSerializer]]


class LoyaltyPlanJourneyFieldsSerializer(BaseModel, extra=Extra.forbid):
    loyalty_plan_id: int
    join_fields: Optional[JourneyFieldsByClassSerializer]
    register_ghost_card_fields: Optional[JourneyFieldsByClassSerializer]
    add_fields: Optional[JourneyFieldsByClassSerializer]
    authorise_fields: Optional[JourneyFieldsByClassSerializer]


class TokenSerializer(BaseModel, extra=Extra.forbid):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: list

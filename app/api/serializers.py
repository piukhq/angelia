from typing import List, Optional

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Extra, Field, validator

from app.handlers.loyalty_plan import LoyaltyPlanJourney


class BaseModel(PydanticBaseModel):
    """validators to convert empty string and dicts to None. Validators are only run if a value is provided
    for the field. For the conversion to work, the field must be Optional to allow None values."""

    @validator("*", pre=True)
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

    @validator("*", pre=True)
    def empty_dict_to_none(cls, v):
        if v == {}:
            return None
        return v

    @validator("*", pre=True)
    def not_none_lists(cls, v, field):
        if field.default_factory == list and v is None:
            return list()
        else:
            return v


class TokenSerializer(BaseModel, extra=Extra.forbid):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: list


class LoyaltyCardSerializer(BaseModel):
    id: int


# This is just to allow inheriting other models whilst still having loyalty_plan_id as
# the first field, since output order is based on order of field definition.
class LoyaltyPlanIdSerializer(BaseModel, extra=Extra.forbid):
    loyalty_plan_id: int


class PaymentCardSerializer(BaseModel, extra=Extra.forbid):
    id: int
    status: Optional[str]
    name_on_card: str
    card_nickname: Optional[str]
    issuer: Optional[str]
    expiry_month: str
    expiry_year: str


class AlternativeCredentialSerializer(BaseModel, extra=Extra.forbid):
    order: Optional[int]
    display_label: Optional[str]
    validation: Optional[str]
    description: Optional[str]
    credential_slug: Optional[str]
    type: Optional[str]
    is_sensitive: bool
    choice: Optional[List[str]] = Field(default_factory=list)


class CredentialSerializer(BaseModel, extra=Extra.forbid):
    order: Optional[int]
    display_label: Optional[str]
    validation: Optional[str]
    description: Optional[str]
    credential_slug: Optional[str]
    type: Optional[str]
    is_sensitive: bool
    choice: Optional[List[str]] = Field(default_factory=list)
    alternative: Optional[AlternativeCredentialSerializer]


class DocumentSerializer(BaseModel, extra=Extra.forbid):
    order: Optional[int]
    name: Optional[str]
    url: Optional[str]
    description: Optional[str]
    is_acceptance_required: Optional[bool]


class ConsentSerializer(BaseModel, extra=Extra.forbid):
    order: Optional[int]
    consent_slug: Optional[str]
    is_acceptance_required: Optional[bool]
    description: Optional[str]


class JourneyFieldsByClassSerializer(BaseModel, extra=Extra.forbid):
    credentials: Optional[List[CredentialSerializer]] = Field(default_factory=list)
    plan_documents: Optional[List[DocumentSerializer]] = Field(default_factory=list)
    consents: Optional[List[ConsentSerializer]] = Field(default_factory=list)


class JourneyFieldsSerializer(BaseModel, extra=Extra.forbid):
    join_fields: Optional[JourneyFieldsByClassSerializer]
    register_ghost_card_fields: Optional[JourneyFieldsByClassSerializer]
    add_fields: Optional[JourneyFieldsByClassSerializer]
    authorise_fields: Optional[JourneyFieldsByClassSerializer]


class LoyaltyPlanJourneyFieldsSerializer(JourneyFieldsSerializer, LoyaltyPlanIdSerializer, extra=Extra.forbid):
    pass


class PlanFeaturesJourneySerializer(BaseModel, extra=Extra.forbid):
    type: int
    description: LoyaltyPlanJourney


class PlanFeaturesSerializer(BaseModel, extra=Extra.forbid):
    has_points: bool
    has_transactions: bool
    plan_type: Optional[int]
    barcode_type: Optional[int]
    colour: Optional[str]
    journeys: list[PlanFeaturesJourneySerializer] = Field(default_factory=list)


class ImageSerializer(BaseModel, extra=Extra.forbid):
    id: int
    type: Optional[int]
    url: Optional[str]
    description: Optional[str]
    encoding: Optional[str]


class PlanDetailTierSerializer(BaseModel, extra=Extra.forbid):
    name: str
    description: str


class PlanDetailsSerializer(BaseModel, extra=Extra.forbid):
    company_name: Optional[str]
    plan_name: Optional[str]
    plan_label: Optional[str]
    plan_url: Optional[str]
    plan_summary: Optional[str]
    plan_description: Optional[str]
    redeem_instructions: Optional[str]
    plan_register_info: Optional[str]
    join_incentive: Optional[str]
    category: Optional[str]
    tiers: list[PlanDetailTierSerializer] = Field(default_factory=list)


class ContentSerializer(BaseModel, extra=Extra.forbid):
    column: str
    value: str


class LoyaltyPlanSerializer(BaseModel, extra=Extra.forbid):
    loyalty_plan_id: int
    plan_popularity: Optional[int]
    plan_features: PlanFeaturesSerializer
    images: list[ImageSerializer] = Field(default_factory=list)
    plan_details: PlanDetailsSerializer
    journey_fields: JourneyFieldsSerializer
    content: list[ContentSerializer] = Field(default_factory=list)

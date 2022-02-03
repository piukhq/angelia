from typing import List, Optional

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Extra, Field, validator
from pydantic.validators import int_validator

from app.handlers.loyalty_plan import LoyaltyPlanJourney
from app.lib.payment_card import PaymentAccountStatus


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


class EmailUpdateSerializer(BaseModel):
    id: int


# This is just to allow inheriting other models whilst still having loyalty_plan_id as
# the first field, since output order is based on order of field definition.
class LoyaltyPlanIdSerializer(BaseModel, extra=Extra.forbid):
    loyalty_plan_id: int


class PaymentCardSerializer(BaseModel, extra=Extra.forbid):
    id: int
    status: Optional[str]
    name_on_card: Optional[str]
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
    text_colour: Optional[str]
    journeys: list[PlanFeaturesJourneySerializer] = Field(default_factory=list)


class ImageSerializer(BaseModel, extra=Extra.forbid):
    id: int
    type: Optional[int]
    url: Optional[str]
    description: Optional[str]
    encoding: Optional[str]


class LoyaltyPlansImageSerializer(BaseModel, extra=Extra.forbid):
    # merge this back in with ImageSerializer (above) when we add order to Wallet images
    id: int
    type: Optional[int]
    url: Optional[str]
    description: Optional[str]
    encoding: Optional[str]
    order: Optional[int]


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
    is_in_wallet: bool
    plan_popularity: Optional[int]
    plan_features: PlanFeaturesSerializer
    images: list[LoyaltyPlansImageSerializer] = Field(default_factory=list)
    plan_details: PlanDetailsSerializer
    journey_fields: JourneyFieldsSerializer
    content: list[ContentSerializer] = Field(default_factory=list)


class LoyaltyPlanOverviewSerializer(BaseModel, extra=Extra.forbid):
    loyalty_plan_id: int
    is_in_wallet: bool
    plan_name: Optional[str]
    company_name: Optional[str]
    plan_popularity: Optional[int]
    plan_type: Optional[int]
    colour: Optional[str]
    text_colour: Optional[str]
    category: Optional[str]
    images: list[LoyaltyPlansImageSerializer] = Field(default_factory=list)


class LoyaltyCardWalletStatusSerializer(BaseModel, extra=Extra.forbid):
    state: str
    slug: Optional[str]
    description: Optional[str]


class JoinWalletSerializer(BaseModel, extra=Extra.forbid):
    loyalty_card_id: int = Field(alias="id")
    loyalty_plan_id: int
    loyalty_plan_name: str
    status: LoyaltyCardWalletStatusSerializer
    images: list[ImageSerializer] = Field(default_factory=list)


class JoinWalletOverViewSerializer(BaseModel, extra=Extra.forbid):
    loyalty_card_id: int = Field(alias="id")
    loyalty_plan_id: int
    loyalty_plan_name: str
    status: LoyaltyCardWalletStatusSerializer
    images: list[ImageSerializer] = Field(default_factory=list)


class LoyaltyCardWalletBalanceSerializer(BaseModel, extra=Extra.forbid):
    updated_at: Optional[int]
    current_display_value: Optional[str]


class LoyaltyCardWalletTransactionsSerializer(BaseModel, extra=Extra.ignore):
    id: str
    timestamp: Optional[int]
    description: Optional[str]
    display_value: Optional[str]


class LoyaltyCardWalletVouchersSerializer(BaseModel, extra=Extra.forbid):
    state: str
    earn_type: Optional[str]
    reward_text: Optional[str]
    headline: Optional[str]
    voucher_code: Optional[str] = Field(alias="code")
    barcode_type: Optional[int]
    progress_display_text: Optional[str]
    current_value: Optional[str]
    target_value: Optional[str]
    prefix: Optional[str]
    suffix: Optional[str]
    body_text: Optional[str]
    terms_and_conditions: Optional[str] = Field(alias="terms_and_conditions_url")
    issued_date: Optional[str] = Field(alias="date_issued")
    expiry_date: Optional[str]
    redeemed_date: Optional[str] = Field(alias="date_redeemed")


class PllPaymentSchemeSerializer(BaseModel, extra=Extra.forbid):
    payment_account_id: int
    payment_scheme: str
    status: str


class LoyaltyCardWalletCardsSerializer(BaseModel, extra=Extra.forbid):
    barcode: Optional[str]
    barcode_type: Optional[int]
    card_number: Optional[str]
    colour: Optional[str]
    text_colour: Optional[str]


class LoyaltyCardWalletSerializer(BaseModel, extra=Extra.forbid):
    id: int
    loyalty_plan_id: int
    loyalty_plan_name: str
    status: LoyaltyCardWalletStatusSerializer
    balance: LoyaltyCardWalletBalanceSerializer
    transactions: list[LoyaltyCardWalletTransactionsSerializer] = Field(default_factory=list)
    vouchers: list[LoyaltyCardWalletVouchersSerializer] = Field(default_factory=list)
    card: LoyaltyCardWalletCardsSerializer
    images: list[ImageSerializer] = Field(default_factory=list)
    pll_links: list[PllPaymentSchemeSerializer] = Field(default_factory=list)


class LoyaltyCardWalletOverViewSerializer(BaseModel, extra=Extra.forbid):
    id: int
    loyalty_plan_id: int
    loyalty_plan_name: str
    status: LoyaltyCardWalletStatusSerializer
    balance: LoyaltyCardWalletBalanceSerializer
    images: list[ImageSerializer] = Field(default_factory=list)


class PllPaymentLinksSerializer(BaseModel, extra=Extra.forbid):
    loyalty_card_id: int
    loyalty_plan: str
    status: str


class StatusStr(str):
    """
    Contrived example of a special type of date that
    takes an int and interprets it as a day in the current year
    """

    @classmethod
    def __get_validators__(cls):
        yield int_validator
        yield cls.validate

    @classmethod
    def validate(cls, v: int):
        return PaymentAccountStatus.to_str(v)


class PaymentCardWalletSerializer(BaseModel, extra=Extra.forbid):
    id: int
    provider: str
    status: StatusStr
    expiry_month: str
    expiry_year: str
    name_on_card: Optional[str]
    card_nickname: Optional[str]
    images: list[ImageSerializer] = Field(default_factory=list)
    pll_links: list[PllPaymentLinksSerializer] = Field(default_factory=list)


class PaymentCardWalletOverViewSerializer(BaseModel, extra=Extra.forbid):
    id: int
    provider: str
    status: StatusStr
    expiry_month: str
    expiry_year: str
    name_on_card: Optional[str]
    card_nickname: Optional[str]
    images: list[ImageSerializer] = Field(default_factory=list)


class WalletSerializer(BaseModel, extra=Extra.forbid):
    joins: list[JoinWalletSerializer] = Field(default_factory=list)
    loyalty_cards: list[LoyaltyCardWalletSerializer] = Field(default_factory=list)
    payment_accounts: list[PaymentCardWalletSerializer] = Field(default_factory=list)


class WalletOverViewSerializer(BaseModel, extra=Extra.forbid):
    joins: list[JoinWalletOverViewSerializer] = Field(default_factory=list)
    loyalty_cards: list[LoyaltyCardWalletOverViewSerializer] = Field(default_factory=list)
    payment_accounts: list[PaymentCardWalletOverViewSerializer] = Field(default_factory=list)


class WalletLoyaltyCardTransactionsSerializer(BaseModel, extra=Extra.forbid):
    transactions: list[LoyaltyCardWalletTransactionsSerializer] = Field(default_factory=list)


class WalletLoyaltyCardBalanceSerializer(BaseModel, extra=Extra.forbid):
    balance: LoyaltyCardWalletBalanceSerializer


class WalletLoyaltyCardVoucherSerializer(BaseModel, extra=Extra.forbid):
    vouchers: list[LoyaltyCardWalletVouchersSerializer] = Field(default_factory=list)

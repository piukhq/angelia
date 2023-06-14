from collections.abc import Generator
from typing import TYPE_CHECKING

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Extra, Field, validator
from pydantic.validators import int_validator

from app.handlers.loyalty_plan import LoyaltyPlanJourney
from app.lib.payment_card import PaymentAccountStatus

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo


class BaseModel(PydanticBaseModel):
    """validators to convert empty string and dicts to None. Validators are only run if a value is provided
    for the field. For the conversion to work, the field must be Optional to allow None values."""

    @validator("*", pre=True)
    @classmethod
    def empty_str_to_none(cls, v: str) -> str | None:
        return v or None

    @validator("*", pre=True)
    @classmethod
    def empty_dict_to_none(cls, v: dict) -> dict | None:
        return v or None

    @validator("*", pre=True)
    @classmethod
    def not_none_lists(cls, v: list | None, field: "FieldInfo") -> list | None:
        return [] if field.default_factory == list and v is None else v


class TokenSerializer(BaseModel, extra=Extra.forbid):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: list


class LoyaltyCardSerializer(BaseModel):
    id: int  # noqa: A003


class EmailUpdateSerializer(BaseModel):
    id: int  # noqa: A003


# This is just to allow inheriting other models whilst still having loyalty_plan_id as
# the first field, since output order is based on order of field definition.
class LoyaltyPlanIdSerializer(BaseModel, extra=Extra.forbid):
    loyalty_plan_id: int


class PaymentAccountPostSerializer(BaseModel, extra=Extra.forbid):
    id: int  # noqa: A003


class PaymentAccountPatchSerializer(BaseModel, extra=Extra.forbid):
    id: int  # noqa: A003
    status: str | None
    name_on_card: str | None
    card_nickname: str | None
    issuer: str | None
    expiry_month: str
    expiry_year: str


class AlternativeCredentialSerializer(BaseModel, extra=Extra.forbid):
    order: int | None
    display_label: str | None
    validation: str | None
    validation_description: str | None
    description: str | None
    credential_slug: str | None
    type: str | None  # noqa: A003
    is_sensitive: bool
    is_scannable: bool
    is_optional: bool
    choice: list[str] | None = Field(default_factory=list)


class CredentialSerializer(BaseModel, extra=Extra.forbid):
    order: int | None
    display_label: str | None
    validation: str | None
    validation_description: str | None
    description: str | None
    credential_slug: str | None
    type: str | None  # noqa: A003
    is_sensitive: bool
    is_scannable: bool
    is_optional: bool
    choice: list[str] | None = Field(default_factory=list)
    alternative: AlternativeCredentialSerializer | None


class DocumentSerializer(BaseModel, extra=Extra.forbid):
    order: int | None
    name: str | None
    url: str | None
    description: str | None
    is_acceptance_required: bool | None


class ConsentSerializer(BaseModel, extra=Extra.forbid):
    order: int | None
    consent_slug: str | None
    is_acceptance_required: bool | None
    description: str | None


class JourneyFieldsByClassSerializer(BaseModel, extra=Extra.forbid):
    credentials: list[CredentialSerializer] | None = Field(default_factory=list)
    plan_documents: list[DocumentSerializer] | None = Field(default_factory=list)
    consents: list[ConsentSerializer] | None = Field(default_factory=list)


class JourneyFieldsSerializer(BaseModel, extra=Extra.forbid):
    join_fields: JourneyFieldsByClassSerializer | None
    register_ghost_card_fields: JourneyFieldsByClassSerializer | None
    add_fields: JourneyFieldsByClassSerializer | None
    authorise_fields: JourneyFieldsByClassSerializer | None


class LoyaltyPlanJourneyFieldsSerializer(JourneyFieldsSerializer, LoyaltyPlanIdSerializer, extra=Extra.forbid):
    pass


class PlanFeaturesJourneySerializer(BaseModel, extra=Extra.forbid):
    type: int  # noqa: A003
    description: LoyaltyPlanJourney


class PlanFeaturesSerializer(BaseModel, extra=Extra.forbid):
    has_points: bool
    has_transactions: bool
    plan_type: int | None
    barcode_type: int | None
    colour: str | None
    text_colour: str | None
    journeys: list[PlanFeaturesJourneySerializer] = Field(default_factory=list)


class ImageSerializer(BaseModel, extra=Extra.ignore):
    id: int  # noqa: A003
    type: int | None  # noqa: A003
    url: str | None
    description: str | None
    encoding: str | None


class SchemeImageSerializer(ImageSerializer, extra=Extra.forbid):
    cta_url: str | None


class LoyaltyPlansImageSerializer(BaseModel, extra=Extra.forbid):
    # merge this back in with ImageSerializer (above) when we add order to Wallet images
    id: int  # noqa: A003
    type: int | None  # noqa: A003
    url: str | None
    cta_url: str | None
    description: str | None
    encoding: str | None
    order: int | None


class PlanDetailTierSerializer(BaseModel, extra=Extra.forbid):
    name: str
    description: str


class PlanDetailsSerializer(BaseModel, extra=Extra.forbid):
    company_name: str | None
    plan_name: str | None
    plan_label: str | None
    plan_url: str | None
    plan_summary: str | None
    plan_description: str | None
    redeem_instructions: str | None
    plan_register_info: str | None
    join_incentive: str | None
    category: str | None
    tiers: list[PlanDetailTierSerializer] = Field(default_factory=list)
    forgotten_password_url: str | None


class ContentSerializer(BaseModel, extra=Extra.forbid):
    column: str
    value: str


class LoyaltyPlanSerializer(BaseModel, extra=Extra.forbid):
    loyalty_plan_id: int
    is_in_wallet: bool
    plan_popularity: int | None
    plan_features: PlanFeaturesSerializer
    images: list[LoyaltyPlansImageSerializer] = Field(default_factory=list)
    plan_details: PlanDetailsSerializer
    journey_fields: JourneyFieldsSerializer
    content: list[ContentSerializer] = Field(default_factory=list)


class LoyaltyPlanOverviewSerializer(BaseModel, extra=Extra.forbid):
    loyalty_plan_id: int
    is_in_wallet: bool
    plan_name: str | None
    company_name: str | None
    plan_popularity: int | None
    plan_type: int | None
    colour: str | None
    text_colour: str | None
    category: str | None
    images: list[LoyaltyPlansImageSerializer] = Field(default_factory=list)
    forgotten_password_url: str | None


class LoyaltyPlanDetailSerializer(PlanDetailsSerializer, extra=Extra.forbid):
    images: list[LoyaltyPlansImageSerializer] = Field(default_factory=list)
    colour: str | None
    text_colour: str | None


class LoyaltyCardWalletStatusSerializer(BaseModel, extra=Extra.forbid):
    state: str
    slug: str | None
    description: str | None


class PllStatusSerializer(BaseModel, extra=Extra.forbid):
    state: str
    slug: str | None
    description: str | None


class PllPaymentSchemeSerializer(BaseModel, extra=Extra.forbid):
    payment_account_id: int
    payment_scheme: str
    status: PllStatusSerializer


class PllPaymentLinksSerializer(BaseModel, extra=Extra.forbid):
    loyalty_card_id: int
    loyalty_plan: str
    status: PllStatusSerializer


class LoyaltyCardWalletBalanceSerializer(BaseModel, extra=Extra.forbid):
    updated_at: int | None
    current_display_value: str | None
    loyalty_currency_name: str | None
    prefix: str | None
    suffix: str | None
    current_value: str | None
    target_value: str | None


class LoyaltyCardWalletTransactionsSerializer(BaseModel, extra=Extra.ignore):
    id: str  # noqa: A003
    timestamp: int | None
    description: str | None
    display_value: str | None


class PendingVouchersSerializer(BaseModel, extra=Extra.forbid):
    state: str
    earn_type: str | None
    reward_text: str | None
    headline: str | None
    voucher_code: str | None = Field(alias="code")
    barcode_type: int | None
    progress_display_text: str | None
    current_value: str | None
    target_value: str | None
    prefix: str | None
    suffix: str | None
    body_text: str | None
    terms_and_conditions: str | None = Field(alias="terms_and_conditions_url")
    issued_date: str | None = Field(alias="date_issued")
    expiry_date: str | None
    redeemed_date: str | None = Field(alias="date_redeemed")
    conversion_date: str | None


class LoyaltyCardWalletVouchersSerializer(BaseModel, extra=Extra.forbid):
    state: str
    earn_type: str | None
    reward_text: str | None
    headline: str | None
    voucher_code: str | None = Field(alias="code")
    barcode_type: int | None
    progress_display_text: str | None
    current_value: str | None
    target_value: str | None
    prefix: str | None
    suffix: str | None
    body_text: str | None
    terms_and_conditions: str | None = Field(alias="terms_and_conditions_url")
    issued_date: str | None = Field(alias="date_issued")
    expiry_date: str | None
    redeemed_date: str | None = Field(alias="date_redeemed")


class LoyaltyCardWalletCardsSerializer(BaseModel, extra=Extra.forbid):
    barcode: str | None
    barcode_type: int | None
    card_number: str | None
    colour: str | None
    text_colour: str | None


class LoyaltyCardWalletSerializer(BaseModel, extra=Extra.forbid):
    id: int  # noqa: A003
    loyalty_plan_id: int
    loyalty_plan_name: str
    is_fully_pll_linked: bool
    pll_linked_payment_accounts: int
    total_payment_accounts: int
    status: LoyaltyCardWalletStatusSerializer
    balance: LoyaltyCardWalletBalanceSerializer
    transactions: list[LoyaltyCardWalletTransactionsSerializer] = Field(default_factory=list)
    vouchers: list[LoyaltyCardWalletVouchersSerializer] = Field(default_factory=list)
    card: LoyaltyCardWalletCardsSerializer
    reward_available: bool
    images: list[SchemeImageSerializer] = Field(default_factory=list)
    pll_links: list[PllPaymentSchemeSerializer] = Field(default_factory=list)


class PendingVoucherLoyaltyCardWalletSerializer(BaseModel, extra=Extra.forbid):
    id: int  # noqa: A003
    loyalty_plan_id: int
    loyalty_plan_name: str
    is_fully_pll_linked: bool
    pll_linked_payment_accounts: int
    total_payment_accounts: int
    status: LoyaltyCardWalletStatusSerializer
    balance: LoyaltyCardWalletBalanceSerializer
    transactions: list[LoyaltyCardWalletTransactionsSerializer] = Field(default_factory=list)
    vouchers: list[PendingVouchersSerializer] = Field(default_factory=list)
    card: LoyaltyCardWalletCardsSerializer
    reward_available: bool
    images: list[SchemeImageSerializer] = Field(default_factory=list)
    pll_links: list[PllPaymentSchemeSerializer] = Field(default_factory=list)


class LoyaltyCardWalletOverViewSerializer(BaseModel, extra=Extra.forbid):
    id: int  # noqa: A003
    loyalty_plan_id: int
    loyalty_plan_name: str
    is_fully_pll_linked: bool
    pll_linked_payment_accounts: int
    total_payment_accounts: int
    status: LoyaltyCardWalletStatusSerializer
    balance: LoyaltyCardWalletBalanceSerializer
    card: LoyaltyCardWalletCardsSerializer
    reward_available: bool
    images: list[SchemeImageSerializer] = Field(default_factory=list)


class JoinWalletSerializer(BaseModel, extra=Extra.forbid):
    loyalty_card_id: int = Field(alias="id")
    loyalty_plan_id: int
    loyalty_plan_name: str
    status: LoyaltyCardWalletStatusSerializer
    card: LoyaltyCardWalletCardsSerializer
    images: list[SchemeImageSerializer] = Field(default_factory=list)


class JoinWalletOverViewSerializer(BaseModel, extra=Extra.forbid):
    loyalty_card_id: int = Field(alias="id")
    loyalty_plan_id: int
    loyalty_plan_name: str
    status: LoyaltyCardWalletStatusSerializer
    card: LoyaltyCardWalletCardsSerializer
    images: list[SchemeImageSerializer] = Field(default_factory=list)


class StatusStr(str):
    """
    Contrived example of a special type of date that
    takes an int and interprets it as a day in the current year
    """

    @classmethod
    def __get_validators__(cls) -> Generator:
        yield int_validator
        yield cls.validate

    @classmethod
    def validate(cls, v: int) -> str:
        return PaymentAccountStatus.to_str(v)


class PaymentAccountWalletSerializer(BaseModel, extra=Extra.forbid):
    id: int  # noqa: A003
    provider: str
    issuer: str | None
    status: StatusStr
    expiry_month: str
    expiry_year: str
    name_on_card: str | None
    card_nickname: str | None
    type: str | None  # noqa: A003
    currency_code: str | None
    country: str | None
    last_four_digits: str
    images: list[ImageSerializer] = Field(default_factory=list)
    pll_links: list[PllPaymentLinksSerializer] = Field(default_factory=list)


class PaymentAccountWalletOverViewSerializer(BaseModel, extra=Extra.forbid):
    id: int  # noqa: A003
    provider: str
    issuer: str | None
    status: StatusStr
    expiry_month: str
    expiry_year: str
    name_on_card: str | None
    card_nickname: str | None
    type: str | None  # noqa: A003
    currency_code: str | None
    country: str | None
    last_four_digits: str
    images: list[ImageSerializer] = Field(default_factory=list)


class WalletSerializer(BaseModel, extra=Extra.forbid):
    joins: list[JoinWalletSerializer] = Field(default_factory=list)
    loyalty_cards: list[LoyaltyCardWalletSerializer] = Field(default_factory=list)
    payment_accounts: list[PaymentAccountWalletSerializer] = Field(default_factory=list)


class PendingVoucherWalletSerializer(BaseModel, extra=Extra.forbid):
    joins: list[JoinWalletSerializer] = Field(default_factory=list)
    loyalty_cards: list[PendingVoucherLoyaltyCardWalletSerializer] = Field(default_factory=list)
    payment_accounts: list[PaymentAccountWalletSerializer] = Field(default_factory=list)


class WalletOverViewSerializer(BaseModel, extra=Extra.forbid):
    joins: list[JoinWalletOverViewSerializer] = Field(default_factory=list)
    loyalty_cards: list[LoyaltyCardWalletOverViewSerializer] = Field(default_factory=list)
    payment_accounts: list[PaymentAccountWalletOverViewSerializer] = Field(default_factory=list)


class WalletLoyaltyCardTransactionsSerializer(BaseModel, extra=Extra.forbid):
    transactions: list[LoyaltyCardWalletTransactionsSerializer] = Field(default_factory=list)


class WalletLoyaltyCardBalanceSerializer(BaseModel, extra=Extra.forbid):
    balance: LoyaltyCardWalletBalanceSerializer


class WalletLoyaltyCardVoucherSerializer(BaseModel, extra=Extra.forbid):
    vouchers: list[LoyaltyCardWalletVouchersSerializer] = Field(default_factory=list)


class WalletLoyaltyCardPendingVoucherSerializer(BaseModel, extra=Extra.forbid):
    vouchers: list[PendingVouchersSerializer] = Field(default_factory=list)


class WalletLoyaltyCardSerializer(LoyaltyCardWalletSerializer, extra=Extra.forbid):
    pass


class PendingVoucherWalletLoyaltyCardSerializer(PendingVoucherLoyaltyCardWalletSerializer, extra=Extra.forbid):
    pass


class ChannelLinksSerializer(BaseModel, extra=Extra.forbid):
    slug: str
    description: str


class LoyaltyCardChannelLinksSerializer(BaseModel, extra=Extra.forbid):
    id: int  # noqa: A003
    channels: list[ChannelLinksSerializer] = Field(default_factory=list)


class WalletLoyaltyCardsChannelLinksSerializer(BaseModel, extra=Extra.forbid):
    loyalty_cards: list[LoyaltyCardChannelLinksSerializer] = Field(default_factory=list)

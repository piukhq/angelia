from enum import Enum, IntEnum
from typing import Self


class PaymentAccountStatus(IntEnum):
    """
    This is a copy of statuses from the hermes core PaymentCardAccount model
    """

    PENDING = 0
    ACTIVE = 1
    DUPLICATE_CARD = 2
    NOT_PROVIDER_CARD = 3
    INVALID_CARD_DETAILS = 4
    PROVIDER_SERVER_DOWN = 5
    UNKNOWN = 6

    @classmethod
    def to_str(cls, status: Self | int) -> str:
        return cls(status).name.replace("_", " ").lower()


class PllLinkState(IntEnum):
    """
    This is a copy of statuses from the hermes core PaymentCardSchemeEntry model
    """

    PENDING = 0
    ACTIVE = 1
    INACTIVE = 2

    @classmethod
    def to_str(cls, status: Self | int) -> str:
        return cls(status).name.lower()


class WalletPLLStatus(IntEnum):
    PENDING = 0
    ACTIVE = 1
    INACTIVE = 2

    @classmethod
    def get_states(cls) -> tuple:
        return ((cls.PENDING.value, "pending"), (cls.ACTIVE.value, "active"), (cls.INACTIVE.value, "inactive"))


class WalletPLLSlug(Enum):
    # A more detailed status of a PLL Link
    LOYALTY_CARD_PENDING = "LOYALTY_CARD_PENDING"
    LOYALTY_CARD_NOT_AUTHORISED = "LOYALTY_CARD_NOT_AUTHORISED"
    PAYMENT_ACCOUNT_PENDING = "PAYMENT_ACCOUNT_PENDING"
    PAYMENT_ACCOUNT_INACTIVE = "PAYMENT_ACCOUNT_INACTIVE"
    PAYMENT_ACCOUNT_AND_LOYALTY_CARD_INACTIVE = "PAYMENT_ACCOUNT_AND_LOYALTY_CARD_INACTIVE"
    PAYMENT_ACCOUNT_AND_LOYALTY_CARD_PENDING = "PAYMENT_ACCOUNT_AND_LOYALTY_CARD_PENDING"
    UBIQUITY_COLLISION = "UBIQUITY_COLLISION"

    @classmethod
    def get_descriptions(cls) -> tuple:
        return (
            (
                cls.LOYALTY_CARD_PENDING.value,
                "LOYALTY_CARD_PENDING",
                "When the Loyalty Card becomes authorised, the PLL link will automatically go active.",
            ),
            (
                cls.LOYALTY_CARD_NOT_AUTHORISED.value,
                "LOYALTY_CARD_NOT_AUTHORISED",
                "The Loyalty Card is not authorised so no PLL link can be created.",
            ),
            (
                cls.PAYMENT_ACCOUNT_PENDING.value,
                "PAYMENT_ACCOUNT_PENDING",
                "When the Payment Account becomes active, the PLL link will automatically go active.",
            ),
            (
                cls.PAYMENT_ACCOUNT_INACTIVE.value,
                "PAYMENT_ACCOUNT_INACTIVE",
                "The Payment Account is not active so no PLL link can be created.",
            ),
            (
                cls.PAYMENT_ACCOUNT_AND_LOYALTY_CARD_INACTIVE.value,
                "PAYMENT_ACCOUNT_AND_LOYALTY_CARD_INACTIVE",
                "The Payment Account and Loyalty Card are not active/authorised so no PLL link can be created.",
            ),
            (
                cls.PAYMENT_ACCOUNT_AND_LOYALTY_CARD_PENDING.value,
                "PAYMENT_ACCOUNT_AND_LOYALTY_CARD_PENDING",
                "When the Payment Account and the Loyalty Card become active/authorised, "
                "the PLL link will automatically go active.",
            ),
            (
                cls.UBIQUITY_COLLISION.value,
                "UBIQUITY_COLLISION",
                "There is already a Loyalty Card from the same Loyalty Plan linked to this Payment Account.",
            ),
        )

    @classmethod
    def get_status_map(cls) -> tuple:
        return (
            # Payment Card Account Active:  loyalty active, pending, inactive
            (
                (WalletPLLStatus.ACTIVE, ""),
                (WalletPLLStatus.PENDING, cls.LOYALTY_CARD_PENDING.value),
                (WalletPLLStatus.INACTIVE, cls.LOYALTY_CARD_NOT_AUTHORISED.value),
            ),
            # Payment Card Account Pending:  loyalty active, pending, inactive
            (
                (WalletPLLStatus.PENDING, cls.PAYMENT_ACCOUNT_PENDING.value),
                (WalletPLLStatus.PENDING, cls.PAYMENT_ACCOUNT_AND_LOYALTY_CARD_PENDING.value),
                (WalletPLLStatus.INACTIVE, cls.LOYALTY_CARD_NOT_AUTHORISED.value),
            ),
            # Payment Card Account inactive:  loyalty active, pending, inactive
            (
                (WalletPLLStatus.INACTIVE, cls.PAYMENT_ACCOUNT_INACTIVE.value),
                (WalletPLLStatus.INACTIVE, cls.PAYMENT_ACCOUNT_INACTIVE.value),
                (WalletPLLStatus.INACTIVE, cls.PAYMENT_ACCOUNT_AND_LOYALTY_CARD_INACTIVE.value),
            ),
        )

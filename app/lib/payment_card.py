from enum import IntEnum


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

    @staticmethod
    def to_str(status):
        statuses = {
            PaymentAccountStatus.PENDING: "pending",
            PaymentAccountStatus.ACTIVE: "active",
            PaymentAccountStatus.DUPLICATE_CARD: "duplicate card",
            PaymentAccountStatus.NOT_PROVIDER_CARD: "not provider card",
            PaymentAccountStatus.INVALID_CARD_DETAILS: "invalid card details",
            PaymentAccountStatus.PROVIDER_SERVER_DOWN: "provider server down",
            PaymentAccountStatus.UNKNOWN: "unknown",
        }
        return statuses[status]

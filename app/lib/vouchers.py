import enum


# lifted from midas/app/vouchers.py
class VoucherState(enum.Enum):
    ISSUED = 0
    IN_PROGRESS = 1
    EXPIRED = 2
    REDEEMED = 3
    CANCELLED = 4
    PENDING = 5


voucher_state_names = {
    VoucherState.ISSUED: "issued",
    VoucherState.IN_PROGRESS: "inprogress",
    VoucherState.EXPIRED: "expired",
    VoucherState.REDEEMED: "redeemed",
    VoucherState.CANCELLED: "cancelled",
    VoucherState.PENDING: "pending",
}


MAX_INACTIVE = 10

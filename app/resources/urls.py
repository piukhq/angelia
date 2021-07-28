from app.resources.example import Example
from app.resources.livez import LiveZ
from app.resources.loyalty_cards import LoyaltyCardAdd, LoyaltyCardAuthorise
from app.resources.metrics import Metrics
from app.resources.payment_accounts import PaymentAccounts
from app.resources.wallets import Wallet

INTERNAL_END_POINTS = {
    "/livez": (LiveZ,),
    "/metrics": (Metrics,),
}

RESOURCE_END_POINTS = {
    "/examples": (Example,),
    "/examples/{id1}/sometext/{id2}": (Example,),
    "/wallets": (Wallet,),
    "/loyalty_cards/adds": (LoyaltyCardAuthorise,),
    "/loyalty_cards": (LoyaltyCardAdd,),
    "/payment_accounts": (PaymentAccounts,),
    "/payment_accounts/{payment_account_id:int}": (PaymentAccounts, {"suffix": "by_id"}),
}

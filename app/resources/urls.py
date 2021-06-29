from app.resources.example import Example
from app.resources.livez import LiveZ
from app.resources.loyalty_cards import LoyaltyAdds
from app.resources.payment_accounts import PaymentAccounts
from app.resources.wallets import Wallet

RESOURCE_END_POINTS = {
    "/livez": LiveZ,
    "/examples": Example,
    "/examples/{id1}/sometext/{id2}": Example,
    "/wallets": Wallet,
    "/loyalty_cards/adds": LoyaltyAdds,
    "/payment_accounts": PaymentAccounts
}
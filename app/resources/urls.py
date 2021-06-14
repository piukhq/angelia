from app.resources.example import Example
from app.resources.wallets import Wallet
from app.resources.healthz import HealthZ
from app.resources.loyalty_cards import LoyaltyAdds


RESOURCE_END_POINTS = {
    "/healthz": HealthZ,
    "/examples": Example,
    "/examples/{id1}/sometext/{id2}": Example,
    "/wallets": Wallet,
    "/loyalty_cards/adds": LoyaltyAdds
}
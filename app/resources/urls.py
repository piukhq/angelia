from app.resources.wonger import Wonger
from app.resources.wallet import Wallet
from app.resources.healthz import HealthZ


RESOURCE_END_POINTS = {
    "/healthz": HealthZ,
    "/wonger": Wonger,
    "/wallets": Wallet,
}
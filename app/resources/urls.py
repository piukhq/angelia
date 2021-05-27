from app.resources.example import Example
from app.resources.wallet import Wallet
from app.resources.healthz import HealthZ


RESOURCE_END_POINTS = {
    "/healthz": HealthZ,
    "/examples": Example,
    "/wallets": Wallet,
}
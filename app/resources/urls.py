from app.resources.example import Example
from app.resources.wallet import Wallet
from app.resources.livez import LiveZ


RESOURCE_END_POINTS = {
    "/livez": LiveZ,
    "/examples": Example,
    "/wallets": Wallet,
}
from app.resources.example import Example
from app.resources.livez import LiveZ
from app.resources.wallet import Wallet

RESOURCE_END_POINTS = {
    "/livez": LiveZ,
    "/examples": Example,
    "/wallets": Wallet,
}

from app.handlers.loyalty_card import ADD, ADD_AND_AUTHORISE
from app.resources.example import Example
from app.resources.livez import LiveZ
from app.resources.loyalty_cards import LoyaltyCard
from app.resources.metrics import Metrics
from app.resources.payment_accounts import PaymentAccounts
from app.resources.wallets import Wallet
from settings import URL_PREFIX


def path(url, resource, url_prefix=URL_PREFIX, **kwargs):
    return {"url": url, "resource": resource, "url_prefix": url_prefix, "kwargs": kwargs}


INTERNAL_END_POINTS = [
    path("/livez", LiveZ, url_prefix=""),
    path("/metrics", Metrics, url_prefix=""),
]


RESOURCE_END_POINTS = [
    path("/examples", Example),
    path("/examples/{id1}/sometext/{id2}", Example),
    path("/wallets", Wallet),
    path("/loyalty_cards/add", LoyaltyCard, suffix="add", journey=ADD),
    path("/loyalty_cards/add_and_authorise", LoyaltyCard, suffix="add_and_auth", journey=ADD_AND_AUTHORISE),
    path("/payment_accounts", PaymentAccounts),
    path("/payment_accounts/{payment_account_id:int}", PaymentAccounts, suffix="by_id"),
]

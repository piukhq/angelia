from typing import Any

from angelia.resources.livez import LiveZ
from angelia.resources.loyalty_cards import LoyaltyCard
from angelia.resources.loyalty_plans import LoyaltyPlanJourneyFields, LoyaltyPlans
from angelia.resources.metrics import Metrics
from angelia.resources.payment_accounts import PaymentAccounts
from angelia.resources.readyz import ReadyZ
from angelia.resources.token import Token
from angelia.resources.users import User
from angelia.resources.wallet import Wallet, WalletRetailer
from angelia.settings import settings


def path(url: str, resource: object, url_prefix: str = settings.URL_PREFIX, **kwargs: Any) -> dict:
    return {"url": url, "resource": resource, "url_prefix": url_prefix, "kwargs": kwargs}


INTERNAL_END_POINTS = [
    path("/livez", LiveZ, url_prefix=""),
    path("/readyz", ReadyZ, url_prefix=""),
    path("/metrics", Metrics, url_prefix=""),
]

RESOURCE_END_POINTS = [
    path("/wallet", Wallet),
    path("/wallet/create_trusted", WalletRetailer, suffix="create_trusted"),
    path("/wallet_overview", Wallet, suffix="overview"),
    path("/wallet/loyalty_cards/{loyalty_card_id:int(min=1)}", Wallet, suffix="loyalty_card_by_id"),
    path("/wallet/payment_account_channel_links", Wallet, suffix="payment_account_channel_links"),
    path("/loyalty_cards/{loyalty_card_id:int(min=1)}/transactions", Wallet, suffix="loyalty_card_transactions"),
    path("/loyalty_cards/{loyalty_card_id:int(min=1)}/balance", Wallet, suffix="loyalty_card_balance"),
    path("/loyalty_cards/{loyalty_card_id:int(min=1)}/vouchers", Wallet, suffix="loyalty_card_vouchers"),
    path("/loyalty_cards/add", LoyaltyCard, suffix="add"),
    path("/loyalty_cards/add_trusted", LoyaltyCard, suffix="trusted_add"),
    path("/loyalty_cards/{loyalty_card_id:int(min=1)}/add_trusted", LoyaltyCard, suffix="trusted_add"),
    path("/loyalty_cards/add_and_authorise", LoyaltyCard, suffix="add_and_auth"),
    path("/loyalty_cards/{loyalty_card_id:int(min=1)}/authorise", LoyaltyCard, suffix="authorise"),
    path("/loyalty_cards/add_and_register", LoyaltyCard, suffix="add_and_register"),
    path("/loyalty_cards/{loyalty_card_id:int(min=1)}/register", LoyaltyCard, suffix="register"),
    path("/email_update", User, suffix="email_update"),
    path("/loyalty_cards/join", LoyaltyCard, suffix="join"),
    path("/loyalty_cards/{loyalty_card_id:int(min=1)}/join", LoyaltyCard, suffix="join_by_id"),
    path("/loyalty_cards/{loyalty_card_id:int(min=1)}", LoyaltyCard, suffix="by_id"),
    path("/loyalty_plans", LoyaltyPlans),
    path("/loyalty_plans_overview", LoyaltyPlans, suffix="overview"),
    path("/loyalty_plans/{loyalty_plan_id:int(min=1)}", LoyaltyPlans, suffix="by_id"),
    path("/loyalty_plans/{loyalty_plan_id:int(min=1)}/plan_details", LoyaltyPlans, suffix="plan_details"),
    path("/loyalty_plans/{loyalty_plan_id:int(min=1)}/journey_fields", LoyaltyPlanJourneyFields, suffix="by_id"),
    path("/me", User),
    path("/payment_accounts", PaymentAccounts),
    path("/payment_accounts/{payment_account_id:int(min=1)}", PaymentAccounts, suffix="by_id"),
    path("/token", Token),
]

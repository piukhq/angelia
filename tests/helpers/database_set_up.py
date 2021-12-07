import typing

from app.hermes.models import PaymentAccountUserAssociation, SchemeChannelAssociation
from tests.factories import (
    ChannelFactory,
    ClientApplicationFactory,
    LoyaltyCardFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanFactory,
    OrganisationFactory,
    PaymentAccountFactory,
    PaymentCardFactory,
    UserFactory,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


def setup_database(db_session: "Session") -> tuple:
    channels = {}
    users = {}

    for name in ["bank1", "bank2", "bank3"]:
        org = OrganisationFactory(name=name)
        bundle_id = f"com.{name}.test"
        client = ClientApplicationFactory(organisation=org, name=name, client_id=f"213124_{name}_3883248")
        channels[bundle_id] = ChannelFactory(bundle_id=bundle_id, client_application=client)
        for i in range(0, 3):
            users[f"{name}_{i}"] = UserFactory(client=channels[bundle_id].client_application)
            db_session.flush()
    db_session.commit()
    return channels, users


def set_up_loyalty_plans(db_session: "Session", channels: dict) -> dict:
    loyalty_plans = {}

    for slug in ["merchant_1", "merchant_2"]:
        loyalty_plans[slug] = LoyaltyPlanFactory(slug=slug)
        db_session.flush()

    for slug, plan in loyalty_plans.items():
        for bundle_id, channel in channels.items():
            sca = SchemeChannelAssociation(status=0, bundle_id=channel.id, scheme_id=plan.id, test_scheme=False)
            db_session.add(sca)

    db_session.commit()
    return loyalty_plans


def set_up_payment_cards(db_session: "Session") -> dict:
    payment_cards = {}

    for slug in ["bankcard1", "bankcard2"]:
        payment_cards[slug] = PaymentCardFactory(slug=slug)
        db_session.flush()

    db_session.commit()
    return payment_cards


def setup_loyalty_cards(
    db_session: "Session",
    users: dict,
    loyalty_plans: dict,
    balances: list = None,
    vouchers: list = None,
    transactions: list = None,
    for_user: str = None,
) -> dict:
    loyalty_cards = {}

    # Add a loyalty card for each user
    for user_name, user in users.items():
        card_number = f"951114320013354045551{user.id}"
        loyalty_cards[user_name] = {}
        if for_user == user_name:
            set_balances = balances
            set_vouchers = vouchers
            set_transactions = transactions
        else:
            set_balances = set_vouchers = set_transactions = []
        loyalty_cards[user_name]["merchant_1"] = LoyaltyCardFactory(
            scheme=loyalty_plans["merchant_1"],
            card_number=card_number,
            main_answer=card_number,
            status=1,
            balances=set_balances,
            vouchers=set_vouchers,
            transactions=set_transactions,
        )
        db_session.flush()
        LoyaltyCardUserAssociationFactory(
            scheme_account_id=loyalty_cards[user_name]["merchant_1"].id, user_id=user.id, auth_provided=True
        )
        db_session.flush()
        card_number = f"951114320013354045552{user.id}"
        loyalty_cards[user_name]["merchant_2"] = LoyaltyCardFactory(
            scheme=loyalty_plans["merchant_2"], card_number=card_number, main_answer=card_number, status=10
        )
        db_session.flush()
        LoyaltyCardUserAssociationFactory(
            scheme_account_id=loyalty_cards[user_name]["merchant_2"].id, user_id=user.id, auth_provided=False
        )
        db_session.flush()
    db_session.commit()
    return loyalty_cards


def setup_payment_accounts(db_session: "Session", users: dict, payment_card: dict) -> dict:
    payment_accounts = {}
    # Add a payment account for each user
    for user_name, user in users.items():
        payment_accounts[user_name] = {}
        payment_accounts[user_name]["bankcard1"] = PaymentAccountFactory(
            payment_card=payment_card["bankcard1"], status=1
        )
        db_session.flush()
        payment_account_user_association = PaymentAccountUserAssociation(
            payment_card_account_id=payment_accounts[user_name]["bankcard1"].id, user_id=user.id
        )
        db_session.add(payment_account_user_association)

    db_session.commit()
    return payment_accounts

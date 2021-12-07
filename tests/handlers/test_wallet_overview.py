import typing

from app.handlers.wallet import WalletHandler
from tests.handlers.test_wallet_handler import (
    set_up_loyalty_plans,
    set_up_payment_cards,
    setup_database,
    setup_loyalty_cards,
    setup_payment_accounts,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_wallet(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    for resp_pay_account in resp["payment_accounts"]:
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name]["bankcard1"], field)
        assert resp_pay_account["images"] == []

    for resp_loyalty_card in resp["loyalty_cards"]:
        id1 = resp_loyalty_card["id"]
        merchant = None
        if id1 == loyalty_cards[test_user_name]["merchant_1"].id:
            merchant = "merchant_1"
        if id1 == loyalty_cards[test_user_name]["merchant_2"].id:
            merchant = "merchant_2"
        assert merchant is not None

        assert resp_loyalty_card["loyalty_plan_id"] == loyalty_cards[test_user_name][merchant].scheme.id
        status = resp_loyalty_card["status"]
        images = resp_loyalty_card["images"]

        assert images == []

        if merchant == "merchant_1":
            assert status["state"] == "authorised"
            assert status["slug"] is None
            assert status["description"] is None
        elif merchant == "merchant_2":
            assert status["state"] == "pending"
            assert status["slug"] == "WALLET_ONLY"
            assert status["description"] == "No authorisation provided"
        else:
            assert False

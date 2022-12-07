import typing
from datetime import datetime, timedelta
from urllib.parse import urljoin

from app.handlers.loyalty_plan import LoyaltyPlanChannelStatus
from app.handlers.wallet import WalletHandler
from app.lib.images import ImageStatus, ImageTypes
from app.lib.loyalty_card import LoyaltyCardStatus, StatusName
from settings import CUSTOM_DOMAIN
from tests.helpers.database_set_up import (
    set_up_loyalty_plans,
    set_up_payment_cards,
    setup_database,
    setup_loyalty_account_images,
    setup_loyalty_card_images,
    setup_loyalty_cards,
    setup_loyalty_scheme_override,
    setup_payment_accounts,
    setup_payment_card_account_images,
    setup_payment_card_images,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_wallet_overview_no_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a user's wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    # see if both payment cards only belonging to our user are listed
    assert len(resp["payment_accounts"]) == 2
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)
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

        assert resp_loyalty_card["is_fully_pll_linked"] is False
        assert resp_loyalty_card["total_payment_accounts"] == len(resp["payment_accounts"])
        assert resp_loyalty_card["pll_linked_payment_accounts"] == 0
        assert resp_loyalty_card["reward_available"] is False


def test_wallet_overview_with_scheme_error_override(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    setup_loyalty_cards(db_session, users, loyalty_plans)

    test_user_name = "bank2_2"
    test_loyalty_plan = "merchant_1"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    override = setup_loyalty_scheme_override(
        db_session,
        loyalty_plan_id=loyalty_plans[test_loyalty_plan].id,
        channel_id=channel.id,
        error_code=LoyaltyCardStatus.ACTIVE,
    )

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    for x in resp["loyalty_cards"]:
        if x["loyalty_plan_id"] == loyalty_plans[test_loyalty_plan].id:
            assert x["status"]["state"] == StatusName.AUTHORISED
            assert x["status"]["slug"] == override["slug"]
            assert x["status"]["description"] == override["message"]


def test_wallet_overview_plan_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    loyalty_images = setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    payment_card_images = setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    # see if both payment cards only belonging to our user are listed
    assert len(resp["payment_accounts"]) == 2
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)
        bank = resp_pay_account["card_nickname"]
        image = resp_pay_account["images"][0]
        assert image["id"] == payment_card_images[bank].id
        assert image["description"] == payment_card_images[bank].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", payment_card_images[bank].image)

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
        for field in ["description", "id"]:
            assert images[0][field] == getattr(loyalty_images[merchant], field)
        assert images[0]["url"] == urljoin(f"{CUSTOM_DOMAIN}/", loyalty_images[merchant].image)

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


def test_wallet_overview_account_override_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    loyalty_images = setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    payment_card_images = setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    loyalty_account_images = setup_loyalty_account_images(
        db_session,
        loyalty_cards,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:
    payment_account_images = setup_payment_card_account_images(
        db_session,
        payment_accounts,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)
        bank = resp_pay_account["card_nickname"]
        image = resp_pay_account["images"][0]
        assert image["id"] != payment_card_images[bank].id
        assert image["description"] != payment_card_images[bank].description
        assert image["url"] != urljoin(f"{CUSTOM_DOMAIN}/", payment_card_images[bank].image)

        assert image["id"] == payment_account_images[test_user_name][account_id].id + 10000000
        assert image["description"] == payment_account_images[test_user_name][account_id].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", payment_account_images[test_user_name][account_id].image)

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
        image = resp_loyalty_card["images"][0]
        assert image["id"] != loyalty_images[merchant].id
        assert image["description"] != loyalty_images[merchant].description
        assert image["url"] != urljoin(f"{CUSTOM_DOMAIN}/", loyalty_images[merchant].image)
        assert image["id"] == loyalty_account_images[test_user_name][merchant].id + 10000000
        assert image["description"] == loyalty_account_images[test_user_name][merchant].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", loyalty_account_images[test_user_name][merchant].image)

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


def test_wallet_overview_account_no_override_not_started_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    loyalty_images = setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    payment_card_images = setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    loyalty_account_images = setup_loyalty_account_images(
        db_session,
        loyalty_cards,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() + timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:
    payment_account_images = setup_payment_card_account_images(
        db_session,
        payment_accounts,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() + timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)
        bank = resp_pay_account["card_nickname"]
        image = resp_pay_account["images"][0]
        assert image["id"] == payment_card_images[bank].id
        assert image["description"] == payment_card_images[bank].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", payment_card_images[bank].image)

        assert image["id"] != payment_account_images[test_user_name][account_id].id + 10000000
        assert image["description"] != payment_account_images[test_user_name][account_id].description
        assert image["url"] != urljoin(f"{CUSTOM_DOMAIN}/", payment_account_images[test_user_name][account_id].image)

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
        image = resp_loyalty_card["images"][0]
        assert image["id"] == loyalty_images[merchant].id
        assert image["description"] == loyalty_images[merchant].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", loyalty_images[merchant].image)
        assert image["id"] != loyalty_account_images[test_user_name][merchant].id + 10000000
        assert image["description"] != loyalty_account_images[test_user_name][merchant].description
        assert image["url"] != urljoin(f"{CUSTOM_DOMAIN}/", loyalty_account_images[test_user_name][merchant].image)

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


def test_wallet_overview_account_no_override_ended_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    loyalty_images = setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    payment_card_images = setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    loyalty_account_images = setup_loyalty_account_images(
        db_session,
        loyalty_cards,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=30),
        end_date=datetime.today() - timedelta(minutes=10),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:
    payment_account_images = setup_payment_card_account_images(
        db_session,
        payment_accounts,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=30),
        end_date=datetime.today() - timedelta(minutes=10),
    )

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)
        bank = resp_pay_account["card_nickname"]
        image = resp_pay_account["images"][0]
        assert image["id"] == payment_card_images[bank].id
        assert image["description"] == payment_card_images[bank].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", payment_card_images[bank].image)

        assert image["id"] != payment_account_images[test_user_name][account_id].id + 10000000
        assert image["description"] != payment_account_images[test_user_name][account_id].description
        assert image["url"] != urljoin(f"{CUSTOM_DOMAIN}/", payment_account_images[test_user_name][account_id].image)

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
        image = resp_loyalty_card["images"][0]
        assert image["id"] == loyalty_images[merchant].id
        assert image["description"] == loyalty_images[merchant].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", loyalty_images[merchant].image)
        assert image["id"] != loyalty_account_images[test_user_name][merchant].id + 10000000
        assert image["description"] != loyalty_account_images[test_user_name][merchant].description
        assert image["url"] != urljoin(f"{CUSTOM_DOMAIN}/", loyalty_account_images[test_user_name][merchant].image)

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


def test_wallet_overview_account_no_override_draft_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    loyalty_images = setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    payment_card_images = setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    loyalty_account_images = setup_loyalty_account_images(
        db_session,
        loyalty_cards,
        image_type=ImageTypes.HERO,
        status=ImageStatus.DRAFT,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:
    payment_account_images = setup_payment_card_account_images(
        db_session,
        payment_accounts,
        image_type=ImageTypes.HERO,
        status=ImageStatus.DRAFT,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)
        bank = resp_pay_account["card_nickname"]
        image = resp_pay_account["images"][0]
        assert image["id"] == payment_card_images[bank].id
        assert image["description"] == payment_card_images[bank].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", payment_card_images[bank].image)

        assert image["id"] != payment_account_images[test_user_name][account_id].id + 10000000
        assert image["description"] != payment_account_images[test_user_name][account_id].description
        assert image["url"] != urljoin(f"{CUSTOM_DOMAIN}/", payment_account_images[test_user_name][account_id].image)

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
        image = resp_loyalty_card["images"][0]
        assert image["id"] == loyalty_images[merchant].id
        assert image["description"] == loyalty_images[merchant].description
        assert image["url"] == urljoin(f"{CUSTOM_DOMAIN}/", loyalty_images[merchant].image)
        assert image["id"] != loyalty_account_images[test_user_name][merchant].id + 10000000
        assert image["description"] != loyalty_account_images[test_user_name][merchant].description
        assert image["url"] != urljoin(f"{CUSTOM_DOMAIN}/", loyalty_account_images[test_user_name][merchant].image)

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


def test_wallet_overview_plan_not_started_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    setup_loyalty_cards(db_session, users, loyalty_plans)
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() + timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )
    setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() + timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    # see if both payment cards only belonging to our user are listed
    assert len(resp["payment_accounts"]) == 2
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)
        assert resp_pay_account["images"] == []

    for resp_loyalty_card in resp["loyalty_cards"]:
        assert resp_loyalty_card["images"] == []


def test_wallet_overview_plan_ended_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    setup_loyalty_cards(db_session, users, loyalty_plans)
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=30),
        end_date=datetime.today() - timedelta(minutes=10),
    )
    setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=30),
        end_date=datetime.today() - timedelta(minutes=10),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    # see if both payment cards only belonging to our user are listed
    assert len(resp["payment_accounts"]) == 2
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)

        assert resp_pay_account["images"] == []

    for resp_loyalty_card in resp["loyalty_cards"]:

        assert resp_loyalty_card["images"] == []


def test_wallet_overview_plan_draft_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    setup_loyalty_cards(db_session, users, loyalty_plans)
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.DRAFT,
        start_date=datetime.today() - timedelta(minutes=30),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.DRAFT,
        start_date=datetime.today() - timedelta(minutes=30),
        end_date=datetime.today() + timedelta(minutes=10),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    # see if both payment cards only belonging to our user are listed
    assert len(resp["payment_accounts"]) == 2
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)

        assert resp_pay_account["images"] == []

    for resp_loyalty_card in resp["loyalty_cards"]:

        assert resp_loyalty_card["images"] == []


def test_wallet_overview_plan_no_hero_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    setup_loyalty_cards(db_session, users, loyalty_plans)
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.BANNER,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=30),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.BANNER,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=30),
        end_date=datetime.today() + timedelta(minutes=10),
    )

    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert resp["joins"] == []
    # see if both payment cards only belonging to our user are listed
    assert len(resp["payment_accounts"]) == 2
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)

        assert resp_pay_account["images"] == []

    for resp_loyalty_card in resp["loyalty_cards"]:

        assert resp_loyalty_card["images"] == []


def test_wallet_overview_plan_tier_image_override(db_session: "Session"):
    balances = [
        {
            "value": 500.0,
            "prefix": "£",
            "suffix": "",
            "currency": "GBP",
            "updated_at": 1663166482,
            "description": "Placeholder Balance Description",
            "reward_tier": 1,
        }
    ]
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans, balances)
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )

    loyalty_tier_images = setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.TIER,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
        reward_tier=1
    )
    setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )

    setup_payment_accounts(db_session, users, payment_card)

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    for resp_loyalty_card in resp["loyalty_cards"]:
        id1 = resp_loyalty_card["id"]
        merchant = None
        if id1 == loyalty_cards[test_user_name]["merchant_1"].id:
            merchant = "merchant_1"
        if id1 == loyalty_cards[test_user_name]["merchant_2"].id:
            merchant = "merchant_2"
        assert merchant is not None

        assert resp_loyalty_card["loyalty_plan_id"] == loyalty_cards[test_user_name][merchant].scheme.id
        images = resp_loyalty_card["images"]
        for field in ["description", "id"]:
            assert images[0][field] == getattr(loyalty_tier_images[merchant], field)
        assert images[0]["url"] == urljoin(f"{CUSTOM_DOMAIN}/", loyalty_tier_images[merchant].image)


def test_wallet_overview_filters_inactive(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)

    # set up 2 cards from different schemes
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]
    loyalty_card = loyalty_cards[test_user_name]["merchant_1"]

    for link in channel.scheme_associations:
        if link.scheme_id == loyalty_card.scheme_id:
            link.status = LoyaltyPlanChannelStatus.INACTIVE.value
            db_session.flush()
            break

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_overview_wallet_response()

    assert len(resp["loyalty_cards"]) == 1

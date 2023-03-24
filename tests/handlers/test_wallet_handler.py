import typing
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import urljoin

import pytest

from app.api.exceptions import ResourceNotFoundError
from app.handlers.loyalty_plan import LoyaltyPlanChannelStatus
from app.handlers.wallet import (
    WalletHandler,
    is_reward_available,
    make_display_string,
    process_vouchers,
    voucher_fields,
)
from app.hermes.models import SchemeChannelAssociation
from app.lib.images import ImageStatus, ImageTypes
from app.lib.loyalty_card import LoyaltyCardStatus, StatusName
from app.lib.payment_card import PaymentAccountStatus
from settings import CUSTOM_DOMAIN
from tests.factories import (
    ChannelFactory,
    PaymentAccountFactory,
    PaymentAccountUserAssociationFactory,
    PaymentSchemeAccountAssociationFactory,
    WalletHandlerFactory,
    fake,
)
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
    setup_pll_links,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

test_transactions = [
    {
        "id": 239604,
        "status": "active",
        "amounts": [{"value": 1, "prefix": "", "suffix": "stamps", "currency": "stamps"}],
        "timestamp": 1591788226,
        "description": "Cambridge Petty Cury \u00a38.08",
    },
    {
        "id": 239605,
        "status": "active",
        "amounts": [{"value": 1, "prefix": "", "suffix": "stamps", "currency": "stamps"}],
        "timestamp": 1591788225,
        "description": "Cambridge Petty Cury \u00a342.24",
    },
    {
        "id": 239606,
        "status": "active",
        "amounts": [{"value": 1, "prefix": "", "suffix": "stamps", "currency": "stamps"}],
        "timestamp": 1591788225,
        "description": "Cambridge Petty Cury \u00a320.60",
    },
    {
        "id": 239607,
        "status": "active",
        "amounts": [{"value": 1, "prefix": "", "suffix": "stamps", "currency": "stamps"}],
        "timestamp": 1591788224,
        "description": "Cambridge Petty Cury \u00a329.25",
    },
    {
        "id": 239608,
        "status": "active",
        "amounts": [{"value": 1, "prefix": "", "suffix": "stamps", "currency": "stamps"}],
        "timestamp": 1591788223,
        "description": "Cambridge Petty Cury \u00a317.60",
    },
]

expected_transactions = {
    "transactions": [
        {
            "id": 239604,
            "timestamp": 1591788226,
            "description": "Cambridge Petty Cury £8.08",
            "display_value": "1 stamps",
        },
        {
            "id": 239605,
            "timestamp": 1591788225,
            "description": "Cambridge Petty Cury £42.24",
            "display_value": "1 stamps",
        },
        {
            "id": 239606,
            "timestamp": 1591788225,
            "description": "Cambridge Petty Cury £20.60",
            "display_value": "1 stamps",
        },
        {
            "id": 239607,
            "timestamp": 1591788224,
            "description": "Cambridge Petty Cury £29.25",
            "display_value": "1 stamps",
        },
        {
            "id": 239608,
            "timestamp": 1591788223,
            "description": "Cambridge Petty Cury £17.60",
            "display_value": "1 stamps",
        },
    ]
}

test_vouchers = [
    {
        "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
        "earn": {"type": "stamps", "value": 3.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0},
        "state": "inprogress",
        "subtext": "",
        "headline": "Spend \u00a37.00 or more to get a stamp. Collect 7 stamps to get a"
        " Meal Voucher of up to \u00a37 off your next meal.",
        "body_text": "",
        "barcode_type": 0,
        "terms_and_conditions_url": "",
    },
    {
        "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
        "code": "12YC945M",
        "earn": {"type": "stamps", "value": 7.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0},
        "state": "cancelled",
        "subtext": "",
        "headline": "",
        "body_text": "",
        "date_issued": 1590066834,
        "expiry_date": 1591747140,
        "barcode_type": 0,
        "terms_and_conditions_url": "",
    },
    {
        "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
        "code": "12GL3057",
        "earn": {"type": "stamps", "value": 7.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0},
        "state": "redeemed",
        "subtext": "",
        "headline": "Redeemed",
        "body_text": "",
        "date_issued": 1591788238,
        "expiry_date": 1593647940,
        "barcode_type": 0,
        "date_redeemed": 1591788269,
        "terms_and_conditions_url": "",
    },
    {
        "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
        "code": "12SU8539",
        "earn": {"type": "stamps", "value": 7.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0},
        "state": "issued",
        "subtext": "",
        "headline": "Earned",
        "body_text": "",
        "date_issued": 1591788239,
        "expiry_date": 1640822340,
        "barcode_type": 0,
        "terms_and_conditions_url": "",
    },
    {
        "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
        "code": "12SU8999",
        "earn": {"type": "stamps", "value": 7.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0},
        "state": "pending",
        "subtext": "",
        "headline": "Pending",
        "body_text": "Pending voucher",
        "date_issued": 1591788239,
        "expiry_date": 1640822999,
        "barcode_type": 0,
        "terms_and_conditions_url": "",
        "conversion_date": 1640822800,
    },
]

expected_vouchers = {
    "vouchers": [
        {
            "state": "inprogress",
            "headline": "Spend £7.00 or more to get a stamp. Collect 7 stamps"
            " to get a Meal Voucher of up to £7 off your next meal.",
            "code": None,
            "barcode_type": 0,
            "body_text": "",
            "terms_and_conditions_url": "",
            "date_issued": None,
            "expiry_date": None,
            "date_redeemed": None,
            "earn_type": "stamps",
            "progress_display_text": "3/7 stamps",
            "current_value": "3",
            "target_value": "7",
            "prefix": "",
            "suffix": "stamps",
            "reward_text": "Free Meal",
            "conversion_date": None,
        },
        {
            "state": "cancelled",
            "headline": "",
            "code": "12YC945M",
            "barcode_type": 0,
            "body_text": "",
            "terms_and_conditions_url": "",
            "date_issued": 1590066834,
            "expiry_date": 1591747140,
            "date_redeemed": None,
            "earn_type": "stamps",
            "progress_display_text": "7/7 stamps",
            "current_value": "7",
            "target_value": "7",
            "prefix": "",
            "suffix": "stamps",
            "reward_text": "Free Meal",
            "conversion_date": None,
        },
        {
            "state": "redeemed",
            "headline": "Redeemed",
            "code": "12GL3057",
            "barcode_type": 0,
            "body_text": "",
            "terms_and_conditions_url": "",
            "date_issued": 1591788238,
            "expiry_date": 1593647940,
            "date_redeemed": 1591788269,
            "earn_type": "stamps",
            "progress_display_text": "7/7 stamps",
            "current_value": "7",
            "target_value": "7",
            "prefix": "",
            "suffix": "stamps",
            "reward_text": "Free Meal",
            "conversion_date": None,
        },
        {
            "state": "issued",
            "headline": "Earned",
            "code": "12SU8539",
            "barcode_type": 0,
            "body_text": "",
            "terms_and_conditions_url": "",
            "date_issued": 1591788239,
            "expiry_date": 1640822340,
            "date_redeemed": None,
            "earn_type": "stamps",
            "progress_display_text": "7/7 stamps",
            "current_value": "7",
            "target_value": "7",
            "prefix": "",
            "suffix": "stamps",
            "reward_text": "Free Meal",
            "conversion_date": None,
        },
        {
            "state": "pending",
            "headline": "Pending",
            "code": "12SU8999",
            "barcode_type": 0,
            "body_text": "Pending voucher",
            "terms_and_conditions_url": "",
            "date_issued": 1591788239,
            "expiry_date": 1640822999,
            "date_redeemed": None,
            "earn_type": "stamps",
            "progress_display_text": "7/7 stamps",
            "current_value": "7",
            "target_value": "7",
            "prefix": "",
            "suffix": "stamps",
            "reward_text": "Free Meal",
            "conversion_date": 1640822800,
        },
    ]
}

test_balances = [
    {
        "value": 3,
        "prefix": "",
        "suffix": "stamps",
        "currency": "stamps",
        "updated_at": 1637323977,
        "description": "",
        "reward_tier": 0,
    }
]

expected_balance = {
    "balance": {
        "updated_at": 1637323977,
        "current_display_value": "3 stamps",
        "loyalty_currency_name": "stamps",
        "prefix": "",
        "suffix": "stamps",
        "current_value": "3",
        "target_value": "7",
    }
}


def make_voucher(burn: dict, earn: dict) -> list:
    return [
        {
            "burn": burn,
            "earn": earn,
            "state": "inprogress",
            "subtext": "",
            "headline": "Spend \u00a37 etc",
            "body_text": "",
            "barcode_type": 0,
            "terms_and_conditions_url": "test.com",
        }
    ]


def voucher_verify(processed_vouchers: list, raw_vouchers: list) -> tuple:
    voucher = processed_vouchers[0]
    raw = raw_vouchers[0]
    for check in ["state", "headline", "body_text", "barcode_type", "terms_and_conditions_url"]:
        assert voucher[check] == raw[check]
    return voucher["reward_text"], voucher["progress_display_text"]


def verify_voucher_earn_values(processed_vouchers: list, **kwargs):
    for index, value in kwargs.items():
        assert processed_vouchers[0][index] == value


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
    resp = handler.get_wallet_response()

    for x in resp["loyalty_cards"]:
        if x["loyalty_plan_id"] == loyalty_plans[test_loyalty_plan].id:
            assert x["status"]["state"] == StatusName.AUTHORISED
            assert x["status"]["slug"] == override["slug"]
            assert x["status"]["description"] == override["message"]


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
    resp = handler.get_wallet_response()

    assert resp["joins"] == []
    # see if both payment cards only belonging to our user are listed
    assert len(resp["payment_accounts"]) == 2
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)

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
        if merchant == "merchant_1":
            assert status["state"] == "authorised"
            assert status["slug"] is None
            assert status["description"] is None
            assert resp_loyalty_card["transactions"] == []
            assert resp_loyalty_card["vouchers"] == []
        elif merchant == "merchant_2":
            assert status["state"] == "pending"
            assert status["slug"] == "WALLET_ONLY"
            assert status["description"] == "No authorisation provided"
            assert "transactions" not in resp_loyalty_card
            assert "vouchers" not in resp_loyalty_card
        else:
            assert False

        card = resp_loyalty_card["card"]
        for field in ["barcode", "card_number"]:
            assert card[field] == getattr(loyalty_cards[test_user_name][merchant], field)
        for field in ["barcode_type", "colour"]:
            assert card[field] == getattr(loyalty_plans[merchant], field)

        assert resp_loyalty_card["is_fully_pll_linked"] is False
        assert resp_loyalty_card["total_payment_accounts"] == len(resp["payment_accounts"])
        assert resp_loyalty_card["pll_linked_payment_accounts"] == 0
        assert resp_loyalty_card["reward_available"] is False


def test_wallet_pll(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_cards = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    payment_accounts = setup_payment_accounts(db_session, users, payment_cards)
    setup_pll_links(db_session, payment_accounts, loyalty_cards, users)

    # Data setup now find a users wallet:
    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_wallet_response()
    assert resp["joins"] == []
    # see if both payment cards only belonging to our user are listed
    assert len(resp["payment_accounts"]) == 2
    for resp_pay_account in resp["payment_accounts"]:
        account_id = resp_pay_account["id"]
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name][account_id], field)

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
        if merchant == "merchant_1":
            assert status["state"] == "authorised"
            assert status["slug"] is None
            assert status["description"] is None
            assert resp_loyalty_card["is_fully_pll_linked"] is True
            assert resp_loyalty_card["pll_linked_payment_accounts"] == 2
            assert resp_loyalty_card["transactions"] == []
            assert resp_loyalty_card["vouchers"] == []
        elif merchant == "merchant_2":
            assert status["state"] == "pending"
            assert status["slug"] == "WALLET_ONLY"
            assert status["description"] == "No authorisation provided"
            # This will change if setup_pll_links sets up links according to status
            assert resp_loyalty_card["is_fully_pll_linked"] is True
            assert resp_loyalty_card["pll_linked_payment_accounts"] == 2
            assert "transactions" not in resp_loyalty_card
            assert "vouchers" not in resp_loyalty_card
        else:
            assert False

        card = resp_loyalty_card["card"]
        for field in ["barcode", "card_number"]:
            assert card[field] == getattr(loyalty_cards[test_user_name][merchant], field)
        for field in ["barcode_type", "colour"]:
            assert card[field] == getattr(loyalty_plans[merchant], field)
        assert resp_loyalty_card["total_payment_accounts"] == len(resp["payment_accounts"])


def test_wallet_filters_inactive(db_session: "Session"):
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
    resp = handler.get_wallet_response()

    assert len(resp["loyalty_cards"]) == 1


def test_wallet_loyalty_card_by_id(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp_loyalty_card = handler.get_loyalty_card_by_id_response(loyalty_cards[test_user_name]["merchant_1"].id)

    id1 = resp_loyalty_card["id"]
    merchant = None
    if id1 == loyalty_cards[test_user_name]["merchant_1"].id:
        merchant = "merchant_1"
    if id1 == loyalty_cards[test_user_name]["merchant_2"].id:
        merchant = "merchant_2"
    assert merchant is not None

    assert resp_loyalty_card["loyalty_plan_id"] == loyalty_cards[test_user_name][merchant].scheme.id
    status = resp_loyalty_card["status"]
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
    assert resp_loyalty_card["transactions"] == []
    assert resp_loyalty_card["vouchers"] == []
    card = resp_loyalty_card["card"]
    for field in ["barcode", "card_number"]:
        assert card[field] == getattr(loyalty_cards[test_user_name][merchant], field)
    for field in ["barcode_type", "colour"]:
        assert card[field] == getattr(loyalty_plans[merchant], field)

    assert resp_loyalty_card["is_fully_pll_linked"] is False
    assert resp_loyalty_card["total_payment_accounts"] == 0
    assert resp_loyalty_card["pll_linked_payment_accounts"] == 0
    assert resp_loyalty_card["reward_available"] is False


def test_wallet_loyalty_card_by_id_filters_inactive_scheme(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
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

    with pytest.raises(ResourceNotFoundError):
        handler.get_loyalty_card_by_id_response(loyalty_card.id)


@pytest.mark.parametrize("join_status", LoyaltyCardStatus.JOIN_STATES)
def test_wallet_loyalty_card_by_id_filters_join(db_session: "Session", join_status):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]
    loyalty_card = loyalty_cards[test_user_name]["merchant_1"]

    for assoc in loyalty_card.scheme_account_user_associations:
        assoc.link_status = join_status

    db_session.flush()

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)

    with pytest.raises(ResourceNotFoundError):
        handler.get_loyalty_card_by_id_response(loyalty_card.id)


@patch("app.handlers.wallet.PENDING_VOUCHERS_FLAG", True)
def test_loyalty_card_transactions(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    test_user_name = "bank2_2"
    loyalty_cards = setup_loyalty_cards(
        db_session,
        users,
        loyalty_plans,
        transactions=test_transactions,
        vouchers=test_vouchers,
        balances=test_balances,
        for_user=test_user_name,
    )
    # Data setup now find a users wallet:
    user = users[test_user_name]
    channel = channels["com.bank2.test"]
    card_id = loyalty_cards[test_user_name]["merchant_1"].id
    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_loyalty_card_transactions_response(card_id)
    assert resp == expected_transactions
    resp = handler.get_loyalty_card_vouchers_response(card_id)

    # vouchers come back sorted now so assert they are all in the expected list
    for voucher in resp["vouchers"]:
        if voucher["state"] == "pending":
            assert voucher["code"] == "pending"
            assert not voucher["expiry_date"]
            continue
        assert voucher in expected_vouchers["vouchers"]

    resp = handler.get_loyalty_card_balance_response(card_id)
    assert resp == expected_balance


def test_loyalty_card_transactions_vouchers_balance_non_active_card(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    test_user_name = "bank2_2"
    loyalty_cards = setup_loyalty_cards(
        db_session,
        users,
        loyalty_plans,
        transactions=test_transactions,
        vouchers=test_vouchers,
        balances=test_balances,
        for_user=test_user_name,
    )
    # Data setup now find a users wallet:
    user = users[test_user_name]
    channel = channels["com.bank2.test"]
    loyalty_card = loyalty_cards[test_user_name]["merchant_1"]
    for link in loyalty_card.scheme_account_user_associations:
        link.link_status = LoyaltyCardStatus.WALLET_ONLY
    db_session.commit()

    card_id = loyalty_cards[test_user_name]["merchant_1"].id
    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)

    non_auth_expected_balance = {"balance": {"current_display_value": None, "updated_at": None}}

    resp = handler.get_loyalty_card_transactions_response(card_id)
    assert resp == {"transactions": []}
    resp = handler.get_loyalty_card_vouchers_response(card_id)
    assert resp == {"vouchers": []}
    resp = handler.get_loyalty_card_balance_response(card_id)
    assert resp == non_auth_expected_balance


@patch("app.handlers.wallet.PENDING_VOUCHERS_FLAG", True)
def test_loyalty_card_transactions_vouchers_balance_multi_wallet(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    test_user_name = "bank2_2"
    loyalty_cards = setup_loyalty_cards(
        db_session,
        users,
        loyalty_plans,
        transactions=test_transactions,
        vouchers=test_vouchers,
        balances=test_balances,
        for_user=test_user_name,
    )
    # Data setup now find a users wallet:
    user = users[test_user_name]
    channel = channels["com.bank2.test"]
    card_id = loyalty_cards[test_user_name]["merchant_1"].id
    non_auth_card = loyalty_cards[test_user_name]["merchant_2"]
    for link in non_auth_card.scheme_account_user_associations:
        link.link_status = LoyaltyCardStatus.WALLET_ONLY
    db_session.commit()
    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)

    resp = handler.get_loyalty_card_transactions_response(card_id)
    assert resp == expected_transactions
    resp = handler.get_loyalty_card_vouchers_response(card_id)

    # vouchers come back sorted now so assert they are all in the expected list
    for voucher in resp["vouchers"]:
        if voucher["state"] == "pending":
            assert voucher["code"] == "pending"
            assert not voucher["expiry_date"]
            continue
        assert voucher in expected_vouchers["vouchers"]

    resp = handler.get_loyalty_card_balance_response(card_id)
    assert resp == expected_balance

    # Non auth card
    non_auth_expected_balance = {"balance": {"current_display_value": None, "updated_at": None}}

    resp = handler.get_loyalty_card_transactions_response(non_auth_card.id)
    assert resp == {"transactions": []}
    resp = handler.get_loyalty_card_vouchers_response(non_auth_card.id)
    assert resp == {"vouchers": []}
    resp = handler.get_loyalty_card_balance_response(non_auth_card.id)
    assert resp == non_auth_expected_balance


@pytest.mark.parametrize("join_status", LoyaltyCardStatus.JOIN_STATES)
def test_loyalty_card_transactions_vouchers_balance_join_state_raises_404(join_status, db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    test_user_name = "bank2_2"
    loyalty_cards = setup_loyalty_cards(
        db_session,
        users,
        loyalty_plans,
        transactions=test_transactions,
        vouchers=test_vouchers,
        balances=test_balances,
        for_user=test_user_name,
    )
    # Data setup now find a users wallet:
    user = users[test_user_name]
    channel = channels["com.bank2.test"]
    loyalty_card = loyalty_cards[test_user_name]["merchant_1"]
    for link in loyalty_card.scheme_account_user_associations:
        link.link_status = join_status
    db_session.commit()

    card_id = loyalty_cards[test_user_name]["merchant_1"].id
    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)

    with pytest.raises(ResourceNotFoundError):
        handler.get_loyalty_card_transactions_response(card_id)

    with pytest.raises(ResourceNotFoundError):
        handler.get_loyalty_card_vouchers_response(card_id)

    with pytest.raises(ResourceNotFoundError):
        handler.get_loyalty_card_balance_response(card_id)


@patch("app.handlers.wallet.PENDING_VOUCHERS_FLAG", True)
def test_voucher_count():
    # make 40 vouchers (we need more than 10)
    vouchers = test_vouchers * 10
    assert len(vouchers) == 50
    processed_vouchers = process_vouchers(vouchers, "test.com")
    # 20 issued/inprogress + 10 others remain
    assert len(processed_vouchers) == 40


def test_voucher_url():
    # create a single voucher
    vouchers = make_voucher({}, {})
    # process it
    processed_vouchers = process_vouchers(vouchers, "test.com")
    # extract the one and onely voucher for testing
    voucher = vouchers[0]
    processed_voucher = processed_vouchers[0]
    # check some values
    for check in ["state", "headline", "body_text", "barcode_type", "terms_and_conditions_url"]:
        assert voucher[check] == processed_voucher[check]


@patch("app.handlers.wallet.PENDING_VOUCHERS_FLAG", True)
def test_pending_vouchers():
    pending_voucher = {
        "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
        "code": "12SU8999",
        "earn": {"type": "stamps", "value": 7.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0},
        "state": "pending",
        "subtext": "",
        "headline": "Pending",
        "body_text": "Pending voucher",
        "date_issued": 1591788239,
        "expiry_date": 1640822999,
        "barcode_type": 0,
        "terms_and_conditions_url": "",
        "conversion_date": 1640822800,
    }

    processed_vouchers = process_vouchers([pending_voucher], "test.com")
    processed_voucher = processed_vouchers[0]

    assert processed_voucher["code"] == "pending"
    assert not processed_voucher["expiry_date"]


def test_vouchers_burn_zero_free_meal():
    burn = {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""}
    earn = {"type": "stamps", "value": 0.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free Meal"
    assert progress == "0/7 stamps"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="stamps", current_value="0", target_value="7")


def test_vouchers_burn_none_meal():
    burn = {"type": "voucher", "value": None, "prefix": None, "suffix": "Meal", "currency": ""}
    earn = {"type": "points", "value": 0.0, "prefix": "", "suffix": "points", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward is None
    assert progress == "0/7 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="0", target_value="7")


def test_vouchers_burn_blank_meal():
    burn = {"type": "voucher", "value": None, "prefix": "", "suffix": "Meal", "currency": ""}
    earn = {"type": "points", "value": 0.0, "prefix": "", "suffix": "points", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward is None
    assert progress == "0/7 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="0", target_value="7")


def test_vouchers_burn_none_free():
    burn = {"type": "voucher", "value": None, "prefix": "Free", "suffix": None, "currency": ""}
    earn = {"type": "points", "value": 0.0, "prefix": "", "suffix": "points", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free"
    assert progress == "0/7 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="0", target_value="7")


def test_vouchers_burn_blank_free():
    burn = {"type": "voucher", "value": None, "prefix": "Free", "suffix": "", "currency": ""}
    earn = {"type": "points", "value": 0.0, "prefix": "", "suffix": "points", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free"
    assert progress == "0/7 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="0", target_value="7")


def test_vouchers_earn_none_free_meal_with_0_value():
    """This is what happens if you give a value between free meal"""
    burn = {"type": "voucher", "value": 0, "prefix": "Free", "suffix": "Meal", "currency": ""}
    earn = {"type": "stamps", "value": None, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free 0 Meal"
    assert progress is None
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="stamps", current_value=None, target_value="7")


def test_vouchers_earn_empty_free_meal_with_0_value():
    """Can put string in value for Free Meal,  progress is null if no value"""
    burn = {"type": "voucher", "value": "Free Meal", "prefix": "", "suffix": "", "currency": ""}
    earn = {
        "type": "stamps",
        "value": None,
        "prefix": "anything",
        "suffix": "stamps",
        "currency": "",
        "target_value": 7.0,
    }
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free Meal"
    assert progress is None
    verify_voucher_earn_values(
        processed_vouchers, prefix="anything", suffix="stamps", current_value=None, target_value="7"
    )


def test_vouchers_earn_decimal_stamps_free_meal_with_empty_value():
    burn = {"type": "voucher", "value": "", "prefix": "Free", "suffix": "Meal", "currency": ""}
    earn = {"type": "stamps", "value": 6.66, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free Meal"
    assert progress == "6/7 stamps"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="stamps", current_value="6", target_value="7")


def test_vouchers_earn_decimal_burn_points_0_currency_with_suffix():
    burn = {"type": "currency", "value": 0, "prefix": "£", "suffix": "GBP", "currency": ""}
    earn = {
        "type": "points",
        "value": 6.668905,
        "prefix": "",
        "suffix": "points",
        "currency": "",
        "target_value": 89.978956,
    }
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£0 GBP"
    assert progress == "6.67/89.98 points"
    verify_voucher_earn_values(
        processed_vouchers, prefix="", suffix="points", current_value="6.67", target_value="89.98"
    )


def test_vouchers_earn_integer_points_burn_decimal_currency_without_suffix():
    burn = {"type": "currency", "value": 12.89, "prefix": "£", "suffix": None, "currency": ""}
    earn = {"type": "points", "value": 1.000, "prefix": "", "suffix": "points", "currency": "", "target_value": 45.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£12.89"
    assert progress == "1/45 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="1", target_value="45")


def test_vouchers_earn_integer_pounds_burn_integer_currency_without_suffix():
    burn = {"type": "currency", "value": 12, "prefix": "£", "suffix": None, "currency": ""}
    earn = {
        "type": "currency",
        "value": 1,
        "prefix": "£",
        "suffix": "money vouchers",
        "currency": "",
        "target_value": 45,
    }
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£12"
    assert progress == "£1/£45 money vouchers"
    verify_voucher_earn_values(
        processed_vouchers, prefix="£", suffix="money vouchers", current_value="1", target_value="45"
    )


def test_vouchers_earn_integer_pounds_without_suffix_burn_decimal_currency_without_suffix():
    burn = {"type": "currency", "value": 12.5, "prefix": "£", "suffix": None, "currency": ""}
    earn = {"type": "currency", "value": 1, "prefix": "£", "suffix": None, "currency": "", "target_value": 45}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£12.50"
    assert progress == "£1/£45"
    verify_voucher_earn_values(processed_vouchers, prefix="£", suffix=None, current_value="1", target_value="45")


def test_vouchers_earn_decimal_pounds_without_suffix_burn_decimal_currency_without_suffix():
    burn = {"type": "currency", "value": 12.01, "prefix": "£", "suffix": None, "currency": ""}
    earn = {"type": "currency", "value": 1.56, "prefix": "£", "suffix": None, "currency": "", "target_value": 45.5}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£12.01"
    assert progress == "£1.56/£45.50"
    verify_voucher_earn_values(processed_vouchers, prefix="£", suffix=None, current_value="1.56", target_value="45.50")


def test_vouchers_earn_decimal_stamps_without_suffix_burn_null_currency_without_suffix():
    burn = {"type": "currency", "value": None, "prefix": "£", "suffix": None, "currency": ""}
    earn = {
        "type": "stamps",
        "value": 1.56,
        "prefix": "some prefix",
        "suffix": "some suffix",
        "currency": "",
        "target_value": 45.5,
    }
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward is None
    assert progress == "some prefix 1.56/some prefix 45.5 some suffix"
    verify_voucher_earn_values(
        processed_vouchers, prefix="some prefix", suffix="some suffix", current_value="1.56", target_value="45.5"
    )


def test_vouchers_earn_decimal_stamps_without_suffix_burn_null_stamps():
    burn = {"type": "stamps", "value": None, "prefix": "£", "suffix": "stamps", "currency": ""}
    earn = {
        "type": "stamps",
        "value": 1.56,
        "prefix": "some prefix",
        "suffix": "some suffix",
        "currency": "",
        "target_value": 45.5,
    }
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers, "test.com")
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward is None
    assert progress == "some prefix 1.56/some prefix 45.5 some suffix"
    verify_voucher_earn_values(
        processed_vouchers, prefix="some prefix", suffix="some suffix", current_value="1.56", target_value="45.5"
    )


def test_voucher_barcode_type():
    voucher_barcode_type_none = [
        {
            "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
            "earn": {
                "type": "stamps",
                "value": 3.0,
                "prefix": "",
                "suffix": "stamps",
                "currency": "",
                "target_value": 7.0,
            },
            "state": "inprogress",
            "subtext": "",
            "headline": "Spend \u00a37.00 or more to get a stamp. Collect 7 stamps to get a"
            " Meal Voucher of up to \u00a37 off your next meal.",
            "body_text": "",
            "barcode_type": 9,
            "terms_and_conditions_url": "",
        }
    ]

    voucher_barcode_type_not_none = [
        {
            "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
            "earn": {
                "type": "stamps",
                "value": 3.0,
                "prefix": "",
                "suffix": "stamps",
                "currency": "",
                "target_value": 7.0,
            },
            "state": "inprogress",
            "subtext": "",
            "headline": "Spend \u00a37.00 or more to get a stamp. Collect 7 stamps to get a"
            " Meal Voucher of up to \u00a37 off your next meal.",
            "body_text": "",
            "barcode_type": 2,
            "terms_and_conditions_url": "",
        }
    ]

    processed_vouchers = process_vouchers(voucher_barcode_type_none, "test.com")

    assert not processed_vouchers[0]["barcode_type"]

    processed_vouchers = process_vouchers(voucher_barcode_type_not_none, "test.com")

    assert processed_vouchers[0]["barcode_type"] == voucher_barcode_type_not_none[0]["barcode_type"]


def test_process_voucher_overview():
    voucher_true = [{"state": "inprogress"}, {"state": "issued"}]
    voucher_false = [{"state": "inprogress"}]

    assert is_reward_available(voucher_true, StatusName.AUTHORISED)
    assert not is_reward_available(voucher_false, StatusName.AUTHORISED)
    assert not is_reward_available([{}], StatusName.AUTHORISED)


def test_make_display_empty_value():
    """
    This is used for balance and transaction value displays, Value is blank
    so prefix and suffix are not shown None which maps to null on response
    """
    assert make_display_string({"prefix": "", "value": "", "suffix": ""}) is None
    assert make_display_string({"prefix": "x", "value": "", "suffix": "y"}) is None
    assert make_display_string({"prefix": "£", "value": "", "suffix": None}) is None
    assert make_display_string({"prefix": "£", "value": "", "suffix": ""}) is None
    assert make_display_string({"prefix": "£", "value": "", "suffix": "string"}) is None
    assert make_display_string({"prefix": "", "value": "", "suffix": "points"}) is None
    assert make_display_string({"prefix": "", "value": "", "suffix": "stamps"}) is None


def test_make_display_None_value():
    """
    This is used for balance and transaction value displays, Value is None
    so prefix and suffix are not shown None which maps to null on response
    """
    assert make_display_string({"prefix": None, "value": None, "suffix": None}) is None
    assert make_display_string({"prefix": "x", "value": None, "suffix": "y"}) is None
    assert make_display_string({"prefix": "", "value": None, "suffix": ""}) is None
    assert make_display_string({"prefix": "x", "value": None, "suffix": "y"}) is None
    assert make_display_string({"prefix": "£", "value": None, "suffix": None}) is None
    assert make_display_string({"prefix": "£", "value": None, "suffix": ""}) is None
    assert make_display_string({"prefix": "£", "value": None, "suffix": "string"}) is None
    assert make_display_string({"prefix": "", "value": None, "suffix": "points"}) is None
    assert make_display_string({"prefix": "", "value": None, "suffix": "stamps"}) is None


def test_make_display_zero_integer_value():
    """
    This is used for balance and transaction value displays, Value is 0 integer
    so prefix and suffix are shown
    """
    assert make_display_string({"prefix": "", "value": 0, "suffix": ""}) == "0"
    assert make_display_string({"prefix": "x", "value": 0, "suffix": "y"}) == "x 0 y"
    assert make_display_string({"prefix": "£", "value": 0, "suffix": None}) == "£0"
    assert make_display_string({"prefix": "£", "value": 0, "suffix": ""}) == "£0"
    assert make_display_string({"prefix": "£", "value": 0, "suffix": "string"}) == "£0 string"
    assert make_display_string({"prefix": "", "value": 0, "suffix": "points"}) == "0 points"
    assert make_display_string({"prefix": "", "value": 0, "suffix": "stamps"}) == "0 stamps"


def test_make_display_zero_float_value():
    """
    This is used for balance and transaction value displays, Value is 0.0 FLOAT
    so prefix and suffix are shown
    """
    assert make_display_string({"prefix": "", "value": 0.0, "suffix": ""}) == "0"
    assert make_display_string({"prefix": "x", "value": 0.0, "suffix": "y"}) == "x 0 y"
    assert make_display_string({"prefix": "£", "value": 0.0, "suffix": None}) == "£0"
    assert make_display_string({"prefix": "£", "value": 0.0, "suffix": ""}) == "£0"
    assert make_display_string({"prefix": "£", "value": 0.0, "suffix": "string"}) == "£0 string"
    assert make_display_string({"prefix": "", "value": 0.0, "suffix": "points"}) == "0 points"
    assert make_display_string({"prefix": "", "value": 0.0, "suffix": "stamps"}) == "0 stamps"


def test_make_display_float_value_no_decimals():
    """
    This is used for balance and transaction value displays, Value is 12.0 float
    so prefix and suffix are shown and value has no decimal point
    """
    assert make_display_string({"prefix": "", "value": 12.0, "suffix": ""}) == "12"
    assert make_display_string({"prefix": "x", "value": 12.0, "suffix": "y"}) == "x 12 y"
    assert make_display_string({"prefix": "£", "value": 12.0, "suffix": None}) == "£12"
    assert make_display_string({"prefix": "£", "value": 12.0, "suffix": ""}) == "£12"
    assert make_display_string({"prefix": "£", "value": 12.0, "suffix": "string"}) == "£12 string"
    assert make_display_string({"prefix": "", "value": 12.0, "suffix": "points"}) == "12 points"
    assert make_display_string({"prefix": "", "value": 12.0, "suffix": "stamps"}) == "12 stamps"


def test_make_display_integer_value():
    """
    This is used for balance and transaction value displays, Value is 12 integer
    so prefix and suffix are shown and value has no decimal point
    """
    assert make_display_string({"prefix": "", "value": 12, "suffix": ""}) == "12"
    assert make_display_string({"prefix": "x", "value": 12, "suffix": "y"}) == "x 12 y"
    assert make_display_string({"prefix": "£", "value": 12, "suffix": None}) == "£12"
    assert make_display_string({"prefix": "£", "value": 12, "suffix": ""}) == "£12"
    assert make_display_string({"prefix": "£", "value": 12, "suffix": "string"}) == "£12 string"
    assert make_display_string({"prefix": "", "value": 12, "suffix": "points"}) == "12 points"
    assert make_display_string({"prefix": "", "value": 12, "suffix": "stamps"}) == "12 stamps"


def test_make_display_float_with_decimals_value():
    """
    This is used for balance and transaction value displays, Value is 123.1234 a larger float with decimals
    so prefix and suffix are shown and value has 2 places of decimals unless stamps
    """
    assert make_display_string({"prefix": "", "value": 123.1234, "suffix": ""}) == "123.12"
    assert make_display_string({"prefix": "x", "value": 123.1234, "suffix": "y"}) == "x 123.12 y"
    assert make_display_string({"prefix": "£", "value": 123.1234, "suffix": None}) == "£123.12"
    assert make_display_string({"prefix": "£", "value": 123.1234, "suffix": ""}) == "£123.12"
    assert make_display_string({"prefix": "£", "value": 123.1234, "suffix": "string"}) == "£123.12 string"
    assert make_display_string({"prefix": "$", "value": 123.1234, "suffix": "string"}) == "$123.12 string"
    assert make_display_string({"prefix": "€", "value": 123.1234, "suffix": "string"}) == "€123.12 string"
    assert make_display_string({"prefix": "", "value": 123.1234, "suffix": "points"}) == "123.12 points"
    assert make_display_string({"prefix": "", "value": 123.1234, "suffix": "stamps"}) == "123 stamps"


def test_make_display_negative_float_with_decimals_value():
    """
    This is used for balance and transaction value displays, Value is -123.1234 a larger negative float with decimals
    so prefix and suffix are shown and value has 2 places of decimals unless stamps. Minus sign before currency
    """
    assert make_display_string({"prefix": "", "value": -123.1234, "suffix": ""}) == "-123.12"
    assert make_display_string({"prefix": "x", "value": -123.1234, "suffix": "y"}) == "x -123.12 y"
    assert make_display_string({"prefix": "£", "value": -123.1234, "suffix": None}) == "-£123.12"
    assert make_display_string({"prefix": "£", "value": -123.1234, "suffix": ""}) == "-£123.12"
    assert make_display_string({"prefix": "£", "value": -123.1234, "suffix": "string"}) == "-£123.12 string"
    assert make_display_string({"prefix": "$", "value": -123.1234, "suffix": "string"}) == "-$123.12 string"
    assert make_display_string({"prefix": "€", "value": -123.1234, "suffix": "string"}) == "-€123.12 string"
    assert make_display_string({"prefix": "", "value": -123.1234, "suffix": "points"}) == "-123.12 points"
    assert make_display_string({"prefix": "", "value": -123.1234, "suffix": "stamps"}) == "-123 stamps"


def test_make_display_negative_integer_value():
    """
    This is used for balance and transaction value displays, Value is -123 a larger negative integer
    so prefix and suffix are shown and value has no decimals. Minus sign before currency
    """
    assert make_display_string({"prefix": "", "value": -123, "suffix": ""}) == "-123"
    assert make_display_string({"prefix": "x", "value": -123, "suffix": "y"}) == "x -123 y"
    assert make_display_string({"prefix": "£", "value": -123, "suffix": None}) == "-£123"
    assert make_display_string({"prefix": "£", "value": -123, "suffix": ""}) == "-£123"
    assert make_display_string({"prefix": "£", "value": -123, "suffix": "string"}) == "-£123 string"
    assert make_display_string({"prefix": "$", "value": -123, "suffix": "string"}) == "-$123 string"
    assert make_display_string({"prefix": "€", "value": -123, "suffix": "string"}) == "-€123 string"
    assert make_display_string({"prefix": "", "value": -123, "suffix": "points"}) == "-123 points"
    assert make_display_string({"prefix": "", "value": -123, "suffix": "stamps"}) == "-123 stamps"


def test_wallet_plan_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    loyalty_images = setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.BANNER,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    payment_card_images = setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.ICON,
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
    resp = handler.get_wallet_response()

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


def test_wallet_account_tier_hero_override(db_session: "Session"):
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
    setup_loyalty_cards(db_session, users, loyalty_plans, balances)

    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.TIER,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
        reward_tier=1,
    )
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_wallet_response()

    loyalty_card = resp["loyalty_cards"][0]

    assert len(loyalty_card["images"]) == 1
    assert loyalty_card["images"][0]["type"] == ImageTypes.HERO


def test_wallet_account_override_images(db_session: "Session"):
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
    resp = handler.get_wallet_response()

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
        assert image["url"] != loyalty_images[merchant].image
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


def test_wallet_same_multiple_plan_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_loyalty_account_images(
        db_session,
        loyalty_cards,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() + timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )
    payment_accounts = setup_payment_accounts(db_session, users, payment_card)

    # Set up payment account with the same plan
    setup_payment_accounts(db_session, users, payment_card)

    # Data setup now find a users wallet:
    setup_payment_card_account_images(
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
    resp = handler.get_wallet_response()

    assert len(resp["payment_accounts"]) == 4
    for resp_pay_account in resp["payment_accounts"]:
        assert resp_pay_account["images"]


def test_wallet_same_multiple_plan_matching_images(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    payment_card = set_up_payment_cards(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)

    # Set up same loyalty card with same plan in wallet
    setup_loyalty_cards(db_session, users, loyalty_plans)
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.ICON,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_loyalty_account_images(
        db_session,
        loyalty_cards,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() + timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_wallet_response()

    for loyalty_card in resp["loyalty_cards"]:
        # Makes sure image hasn't been poped in get_image_list when there's a matching plan in the wallet
        assert len(loyalty_card["images"]) == 2


def test_wallet_same_multiple_plan_matching_tier_images(db_session: "Session"):
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

    # Set up same loyalty card with same plan in wallet
    setup_loyalty_cards(db_session, users, loyalty_plans, balances)
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.ICON,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.TIER,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
        reward_tier=1,
    )
    setup_loyalty_card_images(
        db_session,
        loyalty_plans,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_payment_card_images(
        db_session,
        payment_card,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() - timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=10),
    )
    setup_loyalty_account_images(
        db_session,
        loyalty_cards,
        image_type=ImageTypes.HERO,
        status=ImageStatus.PUBLISHED,
        start_date=datetime.today() + timedelta(minutes=10),
        end_date=datetime.today() + timedelta(minutes=20),
    )

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_wallet_response()

    for loyalty_card in resp["loyalty_cards"]:
        # Makes sure image hasn't been poped in get_image_list when there's a matching plan in the wallet
        assert len(loyalty_card["images"]) == 2


def test_wallet_account_no_override_not_started_images(db_session: "Session"):
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
    resp = handler.get_wallet_response()

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


def test_wallet_account_no_override_ended_images(db_session: "Session"):
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
    resp = handler.get_wallet_response()

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


def test_wallet_account_no_override_draft_images(db_session: "Session"):
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
    resp = handler.get_wallet_response()

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


def test_wallet_plan_not_started_images(db_session: "Session"):
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
    resp = handler.get_wallet_response()

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


def test_wallet_plan_ended_images(db_session: "Session"):
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
    resp = handler.get_wallet_response()

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


def test_wallet_plan_draft_images(db_session: "Session"):
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
    resp = handler.get_wallet_response()

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


def setup_loyalty_cards_channel_links(db_session, setup_plan_channel_and_user, setup_loyalty_card):
    """
    Setup to create 3 Users in 2 Channels.

    Wallet 1 (Channel 1) > Loyalty Card 1 + Loyalty Card 2 + Payment Account 1
    Wallet 2 (Channel 2) > Loyalty Card 1 + Payment Account 2
    Wallet 3 (Channel 2) > Loyalty Card 1 + Loyalty Card 2 + Payment Account 3

    All Payment Accounts are linked to the Loyalty Cards in their respective Wallets.
    Both Channels are linked to 2 Loyalty Plans with Active status.
    Loyalty Cards 1 and 2 are of different Loyalty Plans.
    """
    channel1 = ChannelFactory(
        client_application__name=fake.slug(),
        client_application__organisation__name=fake.slug(),
        client_application__client_id=fake.slug(),
    )
    channel2 = ChannelFactory(
        bundle_id="com.test2.channel",
        client_application__name=fake.slug(),
        client_application__organisation__name=fake.slug(),
        client_application__client_id=fake.slug(),
    )

    channels = (channel1, channel2)

    # Setup plan channels and users
    loyalty_plan, channel1, user1 = setup_plan_channel_and_user(
        slug=fake.slug(),
        channel=channel1,
        channel_link=True,
        is_trusted_channel=True,
    )

    loyalty_plan2, channel2, user2 = setup_plan_channel_and_user(
        slug=fake.slug(),
        channel=channel2,
        channel_link=True,
    )

    # Add missing SchemeChannelAssociations for both channels
    sca1 = SchemeChannelAssociation(
        status=LoyaltyPlanChannelStatus.ACTIVE.value,
        bundle_id=channel1.id,
        scheme_id=loyalty_plan2.id,
        test_scheme=False,
    )
    sca2 = SchemeChannelAssociation(
        status=LoyaltyPlanChannelStatus.ACTIVE.value,
        bundle_id=channel2.id,
        scheme_id=loyalty_plan.id,
        test_scheme=False,
    )
    db_session.add(sca1, sca2)

    _, _, user3 = setup_plan_channel_and_user(
        loyalty_plan=loyalty_plan,
        channel=channel2,
    )

    users = (user1, user2, user3)
    loyalty_plans = (loyalty_plan, loyalty_plan2)

    # Add loyalty card to wallets
    loyalty_card, loyalty_card_user_association1 = setup_loyalty_card(
        loyalty_plan,
        user1,
        card_number="998767898765678",
    )

    loyalty_card2, loyalty_card_user_association1_plan2 = setup_loyalty_card(
        loyalty_plan2,
        user1,
        card_number="111111111111",
    )

    _, loyalty_card_user_association2 = setup_loyalty_card(
        loyalty_plan,
        user2,
        loyalty_card=loyalty_card,
        card_number="998767898765678",
    )

    _, loyalty_card_user_association3 = setup_loyalty_card(
        loyalty_plan,
        user3,
        loyalty_card=loyalty_card,
        card_number="998767898765678",
    )

    _, loyalty_card_user_association3_plan2 = setup_loyalty_card(
        loyalty_plan2,
        user3,
        loyalty_card=loyalty_card2,
        card_number="111111111111",
    )

    loyalty_cards = (loyalty_card, loyalty_card2)
    loyalty_user_associations = (
        loyalty_card_user_association1,
        loyalty_card_user_association1_plan2,
        loyalty_card_user_association2,
        loyalty_card_user_association3,
        loyalty_card_user_association3_plan2,
    )

    loyalty_card_user_association1.link_status = LoyaltyCardStatus.ACTIVE
    loyalty_card_user_association2.link_status = LoyaltyCardStatus.ACTIVE
    loyalty_card_user_association3.link_status = LoyaltyCardStatus.ACTIVE
    loyalty_card_user_association1_plan2.link_status = LoyaltyCardStatus.ACTIVE
    loyalty_card_user_association3_plan2.link_status = LoyaltyCardStatus.ACTIVE
    db_session.add(loyalty_card_user_association1, loyalty_card_user_association2)
    db_session.add(loyalty_card_user_association3, loyalty_card_user_association1_plan2)
    db_session.add(loyalty_card_user_association3_plan2)

    # Add payment cards to wallets
    payment_account1 = PaymentAccountFactory(status=PaymentAccountStatus.ACTIVE)
    pa_user_association = PaymentAccountUserAssociationFactory(payment_card_account=payment_account1, user=user1)
    payment_account2 = PaymentAccountFactory(status=PaymentAccountStatus.ACTIVE)
    pa_user_association2 = PaymentAccountUserAssociationFactory(payment_card_account=payment_account2, user=user2)
    payment_account3 = PaymentAccountFactory(status=PaymentAccountStatus.ACTIVE, is_deleted=True)
    pa_user_association3 = PaymentAccountUserAssociationFactory(payment_card_account=payment_account3, user=user3)

    payment_accounts = (payment_account1, payment_account2, payment_account3)
    payment_user_associations = (pa_user_association, pa_user_association2, pa_user_association3)

    # Link payment cards to loyalty card
    payment_scheme_associations = (
        PaymentSchemeAccountAssociationFactory(scheme_account=loyalty_card, payment_card_account=payment_account1),
        PaymentSchemeAccountAssociationFactory(scheme_account=loyalty_card2, payment_card_account=payment_account1),
        PaymentSchemeAccountAssociationFactory(scheme_account=loyalty_card, payment_card_account=payment_account2),
        PaymentSchemeAccountAssociationFactory(scheme_account=loyalty_card, payment_card_account=payment_account3),
        PaymentSchemeAccountAssociationFactory(scheme_account=loyalty_card2, payment_card_account=payment_account3),
    )
    db_session.commit()

    return (
        channels,
        users,
        loyalty_plans,
        loyalty_cards,
        loyalty_user_associations,
        payment_accounts,
        payment_user_associations,
        payment_scheme_associations,
    )


def test_get_loyalty_cards_channel_links_response(db_session, setup_plan_channel_and_user, setup_loyalty_card):
    channels, users, _, loyalty_cards, *_ = setup_loyalty_cards_channel_links(
        db_session, setup_plan_channel_and_user, setup_loyalty_card
    )
    channel_1_resp = {
        "slug": channels[0].bundle_id,
        "description": f"You have a Payment Card in the {channels[0].client_application.name} channel.",
    }
    channel_2_resp = {
        "slug": channels[1].bundle_id,
        "description": f"You have a Payment Card in the {channels[1].client_application.name} channel.",
    }

    # Test
    handler = WalletHandlerFactory(db_session=db_session, channel_id=channels[0].bundle_id, user_id=users[0].id)
    results = handler.get_payment_account_channel_links()

    assert len(results.get("loyalty_cards", [])) == 2
    loyalty_card_ids = [card["id"] for card in results["loyalty_cards"]]
    assert loyalty_cards[0].id in loyalty_card_ids
    assert loyalty_cards[1].id in loyalty_card_ids
    for card in results["loyalty_cards"]:
        if card["id"] == loyalty_cards[0].id:
            assert channel_1_resp in card["channels"]
            assert channel_2_resp in card["channels"]
        elif card["id"] == loyalty_cards[1].id:
            assert channel_1_resp in card["channels"]
            assert channel_2_resp not in card["channels"]


def test_get_loyalty_cards_channel_links_response_multi_channel(
    db_session, setup_plan_channel_and_user, setup_loyalty_card
):
    """Test correct behaviour for a single ClientApplication with multiple channels.

    Since user pools are shared across channels, a single PLL link should return all associated
    channels for the payment account user.
    """
    channels, users, loyalty_plans, loyalty_cards, *_ = setup_loyalty_cards_channel_links(
        db_session, setup_plan_channel_and_user, setup_loyalty_card
    )
    channel1, channel2 = channels
    channel3 = ChannelFactory(bundle_id="com.test.multichannel", client_application=channel1.client_application)
    db_session.flush()

    channel_1_resp = {
        "slug": channels[0].bundle_id,
        "description": f"You have a Payment Card in the {channels[0].client_application.name} channel.",
    }
    channel_2_resp = {
        "slug": channels[1].bundle_id,
        "description": f"You have a Payment Card in the {channels[1].client_application.name} channel.",
    }

    # Test multichannel without scheme bundle association
    handler = WalletHandlerFactory(db_session=db_session, channel_id=channels[0].bundle_id, user_id=users[0].id)
    results = handler.get_payment_account_channel_links()

    assert len(results.get("loyalty_cards", [])) == 2
    loyalty_card_ids = [card["id"] for card in results["loyalty_cards"]]
    assert loyalty_cards[0].id in loyalty_card_ids
    assert loyalty_cards[1].id in loyalty_card_ids
    for card in results["loyalty_cards"]:
        if card["id"] == loyalty_cards[0].id:
            assert channel_1_resp in card["channels"]
            assert channel_2_resp in card["channels"]
        elif card["id"] == loyalty_cards[1].id:
            assert channel_1_resp in card["channels"]
            assert channel_2_resp not in card["channels"]

    # Test multichannel with scheme bundle association
    sca = SchemeChannelAssociation(
        status=LoyaltyPlanChannelStatus.ACTIVE.value,
        bundle_id=channel3.id,
        scheme_id=loyalty_plans[0].id,
        test_scheme=False,
    )
    db_session.add(sca)
    db_session.commit()

    channel_3_resp = {
        "slug": channel3.bundle_id,
        "description": f"You have a Payment Card in the {channel3.client_application.name} channel.",
    }

    results = handler.get_payment_account_channel_links()

    assert len(results.get("loyalty_cards", [])) == 2
    loyalty_card_ids = [card["id"] for card in results["loyalty_cards"]]
    assert loyalty_cards[0].id in loyalty_card_ids
    assert loyalty_cards[1].id in loyalty_card_ids
    for card in results["loyalty_cards"]:
        if card["id"] == loyalty_cards[0].id:
            assert channel_1_resp in card["channels"]
            assert channel_2_resp in card["channels"]
            assert channel_3_resp in card["channels"]
        elif card["id"] == loyalty_cards[1].id:
            assert channel_1_resp in card["channels"]
            assert channel_2_resp not in card["channels"]


def test_get_loyalty_cards_channel_links_filters_deleted_cards(
    db_session, setup_plan_channel_and_user, setup_loyalty_card
):
    """Tests the unlikely scenario of a loyalty/payment card being linked to a card that is marked as deleted"""
    pass


@pytest.mark.parametrize("scheme_bundle_status", LoyaltyPlanChannelStatus)
def test_get_loyalty_cards_channel_links_filters_schemes_by_status(
    db_session, setup_plan_channel_and_user, setup_loyalty_card, scheme_bundle_status
):
    """Test loyalty cards linked to the user are not returned if the scheme is inactive"""
    channels, users, _, loyalty_cards, *_ = setup_loyalty_cards_channel_links(
        db_session, setup_plan_channel_and_user, setup_loyalty_card
    )
    channel1, channel2 = channels
    loyalty_card1, loyalty_card2 = loyalty_cards
    for assoc in channel1.scheme_associations:
        if assoc.scheme_id == loyalty_card1.scheme_id:
            assoc.status = scheme_bundle_status
    db_session.commit()

    channel_1_resp = {
        "slug": channels[0].bundle_id,
        "description": f"You have a Payment Card in the {channels[0].client_application.name} channel.",
    }
    channel_2_resp = {
        "slug": channels[1].bundle_id,
        "description": f"You have a Payment Card in the {channels[1].client_application.name} channel.",
    }

    # Test all other statuses are not filtered out
    handler = WalletHandlerFactory(db_session=db_session, channel_id=channels[0].bundle_id, user_id=users[0].id)
    results = handler.get_payment_account_channel_links()

    loyalty_card_ids = [card["id"] for card in results["loyalty_cards"]]
    if scheme_bundle_status == LoyaltyPlanChannelStatus.INACTIVE:
        assert loyalty_cards[0].id not in loyalty_card_ids
        assert loyalty_cards[1].id in loyalty_card_ids

        assert channel_1_resp in results["loyalty_cards"][0]["channels"]
        assert channel_2_resp not in results["loyalty_cards"][0]["channels"]
    else:
        assert len(results.get("loyalty_cards", [])) == 2
        assert loyalty_cards[0].id in loyalty_card_ids
        assert loyalty_cards[1].id in loyalty_card_ids
        for card in results["loyalty_cards"]:
            if card["id"] == loyalty_cards[0].id:
                assert channel_1_resp in card["channels"]
                assert channel_2_resp in card["channels"]
            elif card["id"] == loyalty_cards[1].id:
                assert channel_1_resp in card["channels"]
                assert channel_2_resp not in card["channels"]


def test_get_loyalty_cards_channel_links_does_not_filter_inactive_pll(
    db_session, setup_plan_channel_and_user, setup_loyalty_card
):
    channels, users, _, loyalty_cards, *_, payment_scheme_associations = setup_loyalty_cards_channel_links(
        db_session, setup_plan_channel_and_user, setup_loyalty_card
    )

    loyalty_card1, *_ = loyalty_cards
    assoc = payment_scheme_associations[0]
    assert assoc.scheme_account_id == loyalty_card1.id

    assoc.active_link = False
    db_session.commit()

    channel_1_resp = {
        "slug": channels[0].bundle_id,
        "description": f"You have a Payment Card in the {channels[0].client_application.name} channel.",
    }
    channel_2_resp = {
        "slug": channels[1].bundle_id,
        "description": f"You have a Payment Card in the {channels[1].client_application.name} channel.",
    }

    # Test all other statuses are not filtered out
    handler = WalletHandlerFactory(db_session=db_session, channel_id=channels[0].bundle_id, user_id=users[0].id)
    results = handler.get_payment_account_channel_links()

    assert len(results.get("loyalty_cards", [])) == 2
    loyalty_card_ids = [card["id"] for card in results["loyalty_cards"]]
    assert loyalty_cards[0].id in loyalty_card_ids
    assert loyalty_cards[1].id in loyalty_card_ids
    for card in results["loyalty_cards"]:
        if card["id"] == loyalty_cards[0].id:
            assert channel_1_resp in card["channels"]
            assert channel_2_resp in card["channels"]
        elif card["id"] == loyalty_cards[1].id:
            assert channel_1_resp in card["channels"]
            assert channel_2_resp not in card["channels"]


def test_get_loyalty_cards_channel_links_multi_pcard_same_wallet(
    db_session, setup_plan_channel_and_user, setup_loyalty_card
):
    """
    Tests channels response does not have duplicates when multiple payment cards are linked in the same channel
    """
    channels, users, _, loyalty_cards, *_ = setup_loyalty_cards_channel_links(
        db_session, setup_plan_channel_and_user, setup_loyalty_card
    )
    user1, *_ = users
    loyalty_card1, *_ = loyalty_cards
    new_payment_account = PaymentAccountFactory(status=PaymentAccountStatus.ACTIVE)
    PaymentAccountUserAssociationFactory(payment_card_account=new_payment_account, user=user1)
    PaymentSchemeAccountAssociationFactory(scheme_account=loyalty_card1, payment_card_account=new_payment_account),
    db_session.flush()

    channel_1_resp = {
        "slug": channels[0].bundle_id,
        "description": f"You have a Payment Card in the {channels[0].client_application.name} channel.",
    }
    channel_2_resp = {
        "slug": channels[1].bundle_id,
        "description": f"You have a Payment Card in the {channels[1].client_application.name} channel.",
    }

    # Test
    handler = WalletHandlerFactory(db_session=db_session, channel_id=channels[0].bundle_id, user_id=users[0].id)
    results = handler.get_payment_account_channel_links()

    assert len(results.get("loyalty_cards", [])) == 2
    loyalty_card_ids = [card["id"] for card in results["loyalty_cards"]]
    assert loyalty_cards[0].id in loyalty_card_ids
    assert loyalty_cards[1].id in loyalty_card_ids
    for card in results["loyalty_cards"]:
        if card["id"] == loyalty_cards[0].id:
            assert 2 == len(card["channels"])
            assert channel_1_resp in card["channels"]
            assert channel_2_resp in card["channels"]
        elif card["id"] == loyalty_cards[1].id:
            assert 1 == len(card["channels"])
            assert channel_1_resp in card["channels"]
            assert channel_2_resp not in card["channels"]


@patch("app.handlers.wallet.PENDING_VOUCHERS_FLAG", True)
def test_get_wallet_filters_unauthorised(db_session: "Session"):
    channels, users = setup_database(db_session)
    loyalty_plans = set_up_loyalty_plans(db_session, channels)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)

    for bank in loyalty_cards.values():
        for card in bank.values():
            card.balances = test_balances
            card.vouchers = test_vouchers
            card.transactions = test_transactions

    db_session.commit()

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_wallet_response()

    for card in resp["loyalty_cards"]:
        if card["status"]["state"] == StatusName.AUTHORISED:
            assert expected_balance["balance"] == card["balance"]
            for voucher in card["vouchers"]:
                if voucher["state"] == "pending":
                    assert voucher["code"] == "pending"
                    assert not voucher["expiry_date"]
                    continue
                assert voucher in expected_vouchers["vouchers"]
            assert expected_transactions["transactions"] == card["transactions"]
        else:
            assert {"updated_at": None, "current_display_value": None} == card["balance"]
            assert "transactions" not in card
            assert "vouchers" not in card


def test_voucher_fields():
    expected_fields = [
        "state",
        "headline",
        "code",
        "body_text",
        "terms_and_conditions_url",
        "date_issued",
        "expiry_date",
        "date_redeemed",
    ]

    assert voucher_fields() == expected_fields


@patch("app.handlers.wallet.PENDING_VOUCHERS_FLAG", True)
def test_voucher_fields_with_flag():
    expected_fields = [
        "state",
        "headline",
        "code",
        "body_text",
        "terms_and_conditions_url",
        "date_issued",
        "expiry_date",
        "date_redeemed",
        "conversion_date",
    ]

    assert voucher_fields() == expected_fields

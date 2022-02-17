import typing
from datetime import datetime, timedelta

from app.handlers.wallet import WalletHandler, make_display_string, process_vouchers, process_voucher_overview
from app.lib.images import ImageStatus, ImageTypes
from tests.helpers.database_set_up import (
    set_up_loyalty_plans,
    set_up_payment_cards,
    setup_database,
    setup_loyalty_account_images,
    setup_loyalty_card_images,
    setup_loyalty_cards,
    setup_payment_accounts,
    setup_payment_card_account_images,
    setup_payment_card_images,
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
        "value": 3,
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
    assert resp == expected_vouchers
    resp = handler.get_loyalty_card_balance_response(card_id)
    assert resp == expected_balance


def test_vouchers_burn_zero_free_meal():
    burn = {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""}
    earn = {"type": "stamps", "value": 0.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free Meal"
    assert progress == "0/7 stamps"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="stamps", current_value="0", target_value="7")


def test_vouchers_burn_none_meal():
    burn = {"type": "voucher", "value": None, "prefix": None, "suffix": "Meal", "currency": ""}
    earn = {"type": "points", "value": 0.0, "prefix": "", "suffix": "points", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward is None
    assert progress == "0/7 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="0", target_value="7")


def test_vouchers_burn_blank_meal():
    burn = {"type": "voucher", "value": None, "prefix": "", "suffix": "Meal", "currency": ""}
    earn = {"type": "points", "value": 0.0, "prefix": "", "suffix": "points", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward is None
    assert progress == "0/7 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="0", target_value="7")


def test_vouchers_burn_none_free():
    burn = {"type": "voucher", "value": None, "prefix": "Free", "suffix": None, "currency": ""}
    earn = {"type": "points", "value": 0.0, "prefix": "", "suffix": "points", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free"
    assert progress == "0/7 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="0", target_value="7")


def test_vouchers_burn_blank_free():
    burn = {"type": "voucher", "value": None, "prefix": "Free", "suffix": "", "currency": ""}
    earn = {"type": "points", "value": 0.0, "prefix": "", "suffix": "points", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free"
    assert progress == "0/7 points"
    verify_voucher_earn_values(processed_vouchers, prefix="", suffix="points", current_value="0", target_value="7")


def test_vouchers_earn_none_free_meal_with_0_value():
    """This is what happens if you give a value between free meal"""
    burn = {"type": "voucher", "value": 0, "prefix": "Free", "suffix": "Meal", "currency": ""}
    earn = {"type": "stamps", "value": None, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
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
    processed_vouchers = process_vouchers(raw_vouchers)
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
    processed_vouchers = process_vouchers(raw_vouchers)
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
    processed_vouchers = process_vouchers(raw_vouchers)
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
    processed_vouchers = process_vouchers(raw_vouchers)
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
    processed_vouchers = process_vouchers(raw_vouchers)
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
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£12.50"
    assert progress == "£1/£45"
    verify_voucher_earn_values(processed_vouchers, prefix="£", suffix=None, current_value="1", target_value="45")


def test_vouchers_earn_decimal_pounds_without_suffix_burn_decimal_currency_without_suffix():
    burn = {"type": "currency", "value": 12.01, "prefix": "£", "suffix": None, "currency": ""}
    earn = {"type": "currency", "value": 1.56, "prefix": "£", "suffix": None, "currency": "", "target_value": 45.5}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
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
    processed_vouchers = process_vouchers(raw_vouchers)
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
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward is None
    assert progress == "some prefix 1.56/some prefix 45.5 some suffix"
    verify_voucher_earn_values(
        processed_vouchers, prefix="some prefix", suffix="some suffix", current_value="1.56", target_value="45.5"
    )


def test_process_voucher_overview():
    voucher_true = [{"state": "inprogress"}, {"state": "issued"}]
    voucher_false = [{"state": "inprogress"}]

    assert process_voucher_overview(voucher_true)
    assert not process_voucher_overview(voucher_false)
    assert not process_voucher_overview([{}])


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
        assert image["url"] == payment_card_images[bank].image

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
        assert images[0]["url"] == loyalty_images[merchant].image

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
        assert image["url"] != payment_card_images[bank].image

        assert image["id"] == payment_account_images[test_user_name][account_id].id + 10000000
        assert image["description"] == payment_account_images[test_user_name][account_id].description
        assert image["url"] == payment_account_images[test_user_name][account_id].image

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
        assert image["url"] == loyalty_account_images[test_user_name][merchant].image

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
        assert image["url"] == payment_card_images[bank].image

        assert image["id"] != payment_account_images[test_user_name][account_id].id + 10000000
        assert image["description"] != payment_account_images[test_user_name][account_id].description
        assert image["url"] != payment_account_images[test_user_name][account_id].image

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
        assert image["url"] == loyalty_images[merchant].image
        assert image["id"] != loyalty_account_images[test_user_name][merchant].id + 10000000
        assert image["description"] != loyalty_account_images[test_user_name][merchant].description
        assert image["url"] != loyalty_account_images[test_user_name][merchant].image

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
        assert image["url"] == payment_card_images[bank].image

        assert image["id"] != payment_account_images[test_user_name][account_id].id + 10000000
        assert image["description"] != payment_account_images[test_user_name][account_id].description
        assert image["url"] != payment_account_images[test_user_name][account_id].image

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
        assert image["url"] == loyalty_images[merchant].image
        assert image["id"] != loyalty_account_images[test_user_name][merchant].id + 10000000
        assert image["description"] != loyalty_account_images[test_user_name][merchant].description
        assert image["url"] != loyalty_account_images[test_user_name][merchant].image

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
        assert image["url"] == payment_card_images[bank].image

        assert image["id"] != payment_account_images[test_user_name][account_id].id + 10000000
        assert image["description"] != payment_account_images[test_user_name][account_id].description
        assert image["url"] != payment_account_images[test_user_name][account_id].image

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
        assert image["url"] == loyalty_images[merchant].image
        assert image["id"] != loyalty_account_images[test_user_name][merchant].id + 10000000
        assert image["description"] != loyalty_account_images[test_user_name][merchant].description
        assert image["url"] != loyalty_account_images[test_user_name][merchant].image

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

import typing

from app.handlers.wallet import WalletHandler, make_display_string, process_vouchers
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


def setup_database(db_session: "Session") -> tuple:
    loyalty_plans = {}
    payment_card = {}
    payment_card = {}
    channels = {}
    users = {}

    for slug in ["merchant_1", "merchant_2"]:
        loyalty_plans[slug] = LoyaltyPlanFactory(slug=slug)
        db_session.flush()

    for slug in ["bankcard1", "bankcard2"]:
        payment_card[slug] = PaymentCardFactory(slug=slug)
        db_session.flush()

    for name in ["bank1", "bank2", "bank3"]:
        org = OrganisationFactory(name=name)
        bundle_id = f"com.{name}.test"
        client = ClientApplicationFactory(organisation=org, name=name, client_id=f"213124_{name}_3883248")
        channels[bundle_id] = ChannelFactory(bundle_id=bundle_id, client_application=client)
        for i in range(0, 3):
            users[f"{name}_{i}"] = UserFactory(client=channels[bundle_id].client_application)
            db_session.flush()

    for slug, plan in loyalty_plans.items():
        for bundle_id, channel in channels.items():
            sca = SchemeChannelAssociation(status=0, bundle_id=channel.id, scheme_id=plan.id, test_scheme=False)
            db_session.add(sca)

    db_session.commit()
    return loyalty_plans, payment_card, channels, users


def setup_loyalty_cards(db_session: "Session", users: dict, loyalty_plans: dict) -> dict:
    loyalty_cards = {}

    # Add a loyalty card for each user
    for user_name, user in users.items():
        card_number = f"951114320013354045551{user.id}"
        loyalty_cards[user_name] = {}
        loyalty_cards[user_name]["merchant_1"] = LoyaltyCardFactory(
            scheme=loyalty_plans["merchant_1"], card_number=card_number, main_answer=card_number, status=1
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


def voucher_verify(processed_vouchers: list, raw_vouchers: list) -> tuple:
    voucher = processed_vouchers[0]
    raw = raw_vouchers[0]
    for check in ["state", "headline", "body_text", "barcode_type", "terms_and_conditions_url"]:
        assert voucher[check] == raw[check]
    return voucher["reward_text"], voucher["progress_display_text"]


def test_wallet(db_session: "Session"):
    loyalty_plans, payment_card, channels, users = setup_database(db_session)
    loyalty_cards = setup_loyalty_cards(db_session, users, loyalty_plans)
    payment_accounts = setup_payment_accounts(db_session, users, payment_card)
    # Data setup now find a users wallet:

    test_user_name = "bank2_2"
    user = users[test_user_name]
    channel = channels["com.bank2.test"]

    handler = WalletHandler(db_session, user_id=user.id, channel_id=channel.bundle_id)
    resp = handler.get_response_dict()

    assert resp["joins"] == []
    for resp_pay_account in resp["payment_accounts"]:
        for field in ["card_nickname", "expiry_month", "expiry_year", "id", "name_on_card", "status"]:
            assert resp_pay_account[field] == getattr(payment_accounts[test_user_name]["bankcard1"], field)

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


def test_vouchers_burn_zero_free_meal():
    burn = {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""}
    earn = {"type": "stamps", "value": 0.0, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free Meal"
    assert progress == "0/7 stamps"


def test_vouchers_earn_none_free_meal_with_0_value():
    """This is what happens if you give a value between free meal"""
    burn = {"type": "voucher", "value": 0, "prefix": "Free", "suffix": "Meal", "currency": ""}
    earn = {"type": "stamps", "value": None, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free 0 Meal"
    assert progress is None


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


def test_vouchers_earn_decimal_stamps_free_meal_with_empty_value():
    burn = {"type": "voucher", "value": "", "prefix": "Free", "suffix": "Meal", "currency": ""}
    earn = {"type": "stamps", "value": 6.66, "prefix": "", "suffix": "stamps", "currency": "", "target_value": 7.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "Free Meal"
    assert progress == "6/7 stamps"


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


def test_vouchers_earn_integer_points_burn_decimal_currency_without_suffix():
    burn = {"type": "currency", "value": 12.89, "prefix": "£", "suffix": None, "currency": ""}
    earn = {"type": "points", "value": 1.000, "prefix": "", "suffix": "points", "currency": "", "target_value": 45.0}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£12.89"
    assert progress == "1/45 points"


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


def test_vouchers_earn_integer_pounds_without_suffix_burn_decimal_currency_without_suffix():
    burn = {"type": "currency", "value": 12.5, "prefix": "£", "suffix": None, "currency": ""}
    earn = {"type": "currency", "value": 1, "prefix": "£", "suffix": None, "currency": "", "target_value": 45}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£12.50"
    assert progress == "£1/£45"


def test_vouchers_earn_decimal_pounds_without_suffix_burn_decimal_currency_without_suffix():
    burn = {"type": "currency", "value": 12.01, "prefix": "£", "suffix": None, "currency": ""}
    earn = {"type": "currency", "value": 1.56, "prefix": "£", "suffix": None, "currency": "", "target_value": 45.5}
    raw_vouchers = make_voucher(burn, earn)
    processed_vouchers = process_vouchers(raw_vouchers)
    reward, progress = voucher_verify(processed_vouchers, raw_vouchers)
    assert reward == "£12.01"
    assert progress == "£1.56/£45.50"


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

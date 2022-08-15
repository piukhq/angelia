import pytest

from app.api.serializers import (
    LoyaltyCardWalletBalanceSerializer,
    LoyaltyCardWalletStatusSerializer,
    LoyaltyCardWalletTransactionsSerializer,
    LoyaltyCardWalletVouchersSerializer,
    WalletSerializer,
)


@pytest.fixture
def loyalty_card_status_data():
    return {
        "state": "Active",
        "slug": "active",  # Optional[str]
        "description": "Active",  # Optional[str]
    }


@pytest.fixture
def loyalty_card_balance_data():
    return {
        "updated_at": 1,  # Optional[int]
        "current_display_value": "you have 100 points",  # Optional[str]
        "loyalty_currency_name": "points",  # Optional[str]
        "prefix": "you have",  # Optional[str]
        "suffix": "points",  # Optional[str]
        "current_value": "10",  # Optional[str]
        "target_value": "100",  # Optional[str]
    }


@pytest.fixture
def loyalty_card_transaction_data():
    return {
        "id": "1232134",
        "timestamp": 1,  # Optional[int]
        "description": "Some description",  # Optional[str]
        "display_value": "Some value",  # Optional[str]
    }


@pytest.fixture
def loyalty_card_voucher_data():
    return {
        "state": "redeemed",
        "earn_type": "points",  # Optional[str],
        "reward_text": "get some points",  # Optional[str]
        "headline": "hello",  # Optional[str]
        "code": "yes",  # Optional[str] = Field(alias="code")
        "barcode_type": 1,  # Optional[int]
        "progress_display_text": "this is how to progress",  # Optional[str]
        "current_value": "100",  # Optional[str]
        "target_value": "500",  # Optional[str]
        "prefix": "get some",  # Optional[str]
        "suffix": "points",  # Optional[str]
        "body_text": "here's some points",  # Optional[str]
        "terms_and_conditions_url": "http://some.url",  # Optional[str] = Field(alias="terms_and_conditions_url")
        "date_issued": "12/12/2012",  # Optional[str] = Field(alias="date_issued")
        "expiry_date": "13/12/2012",  # Optional[str]
        "date_redeemed": "12/12/2012",  # Optional[str] = Field(alias="date_redeemed")
    }


@pytest.fixture
def loyalty_card_wallet_card_data():
    return {
        "barcode": "",  # Optional[str]
        "barcode_type": 1,  # Optional[int]
        "card_number": "",  # Optional[str]
        "colour": "",  # Optional[str]
        "text_colour": "",  # Optional[str]
    }


@pytest.fixture
def pll_status_data():
    return {"state": "active", "slug": "", "description": ""}


@pytest.fixture
def pll_payment_scheme_data(pll_status_data):
    return {"payment_account_id": 1, "payment_scheme": "visa", "status": pll_status_data}


@pytest.fixture
def pll_payment_link_data(pll_status_data):
    return {"loyalty_card_id": 1, "loyalty_plan": "Iceland", "status": pll_status_data}


@pytest.fixture
def join_data(loyalty_card_status_data, loyalty_card_wallet_card_data):
    return {
        "id": 1,  # int = Field(alias="id")
        "loyalty_plan_id": 1,
        "loyalty_plan_name": "Iceland",
        "status": loyalty_card_status_data,
        "card": loyalty_card_wallet_card_data,
        "images": [],
    }


@pytest.fixture
def loyalty_card_data(
    loyalty_card_status_data,
    loyalty_card_balance_data,
    loyalty_card_transaction_data,
    loyalty_card_voucher_data,
    loyalty_card_wallet_card_data,
    pll_payment_scheme_data,
):
    return {
        "id": 1,
        "loyalty_plan_id": 1,
        "loyalty_plan_name": "Iceland",
        "is_fully_pll_linked": True,
        "total_payment_accounts": 1,
        "pll_linked_payment_accounts": 1,
        "status": loyalty_card_status_data,
        "balance": loyalty_card_balance_data,
        "transactions": [loyalty_card_transaction_data],
        "vouchers": [loyalty_card_voucher_data],
        "card": loyalty_card_wallet_card_data,
        "images": [],
        "reward_available": False,
        "pll_links": [pll_payment_scheme_data],
    }


@pytest.fixture
def payment_account_data(pll_payment_link_data):
    return {
        "id": 1,
        "provider": "visa",
        "issuer": "HSBC",  # Optional[str]
        "status": 1,
        "expiry_month": "10",
        "expiry_year": "2025",
        "name_on_card": "Binky",  # Optional[str]
        "card_nickname": "Bonkers",  # Optional[str]
        "type": "debit",
        "currency_code": "GBP",
        "country": "GB",
        "last_four_digits": "1234",
        "images": [],
        "pll_links": [pll_payment_link_data],
    }


@pytest.fixture
def wallet_data(join_data, loyalty_card_data, payment_account_data):
    return {
        "joins": [join_data],
        "loyalty_cards": [loyalty_card_data],
        "payment_accounts": [payment_account_data],
    }


def test_wallet_serializer_all_as_expected(wallet_data):
    wallet_serialized = WalletSerializer(**wallet_data).dict()

    expected = {
        "joins": [
            {
                "loyalty_card_id": 1,
                "loyalty_plan_id": 1,
                "loyalty_plan_name": "Iceland",
                "status": {"state": "Active", "slug": "active", "description": "Active"},
                "card": {"barcode": None, "barcode_type": 1, "card_number": None, "colour": None, "text_colour": None},
                "images": [],
            }
        ],
        "loyalty_cards": [
            {
                "id": 1,
                "loyalty_plan_id": 1,
                "loyalty_plan_name": "Iceland",
                "is_fully_pll_linked": True,
                "total_payment_accounts": 1,
                "pll_linked_payment_accounts": 1,
                "status": {"state": "Active", "slug": "active", "description": "Active"},
                "balance": {
                    "updated_at": 1,
                    "current_display_value": "you have 100 points",
                    "loyalty_currency_name": "points",
                    "prefix": "you have",
                    "suffix": "points",
                    "current_value": "10",
                    "target_value": "100",
                },
                "transactions": [
                    {"id": "1232134", "timestamp": 1, "description": "Some description", "display_value": "Some value"}
                ],
                "vouchers": [
                    {
                        "state": "redeemed",
                        "earn_type": "points",
                        "reward_text": "get some points",
                        "headline": "hello",
                        "voucher_code": "yes",
                        "barcode_type": 1,
                        "progress_display_text": "this is how to progress",
                        "current_value": "100",
                        "target_value": "500",
                        "prefix": "get some",
                        "suffix": "points",
                        "body_text": "here's some points",
                        "terms_and_conditions": "http://some.url",
                        "issued_date": "12/12/2012",
                        "expiry_date": "13/12/2012",
                        "redeemed_date": "12/12/2012",
                    }
                ],
                "card": {"barcode": None, "barcode_type": 1, "card_number": None, "colour": None, "text_colour": None},
                "images": [],
                "reward_available": False,
                "pll_links": [
                    {
                        "payment_account_id": 1,
                        "payment_scheme": "visa",
                        "status": {"state": "active", "slug": None, "description": None},
                    }
                ],
            }
        ],
        "payment_accounts": [
            {
                "id": 1,
                "provider": "visa",
                "issuer": "HSBC",
                "status": "active",
                "expiry_month": "10",
                "expiry_year": "2025",
                "name_on_card": "Binky",
                "card_nickname": "Bonkers",
                "type": "debit",
                "currency_code": "GBP",
                "country": "GB",
                "last_four_digits": "1234",
                "images": [],
                "pll_links": [
                    {
                        "loyalty_card_id": 1,
                        "loyalty_plan": "Iceland",
                        "status": {"state": "active", "slug": None, "description": None},
                    }
                ],
            }
        ],
    }
    assert expected == wallet_serialized


def test_loyalty_card_wallet_status_required_fields(loyalty_card_status_data):
    required_data = {"state": loyalty_card_status_data["state"]}
    expected = {
        "state": "Active",
        "slug": None,
        "description": None,
    }
    serialised_status = LoyaltyCardWalletStatusSerializer(**required_data)

    assert serialised_status == expected


def test_loyalty_card_wallet_status_with_optionals(loyalty_card_status_data):
    expected = {
        "state": "Active",
        "slug": "active",
        "description": "Active",
    }
    serialised_status = LoyaltyCardWalletStatusSerializer(**loyalty_card_status_data).dict()

    assert serialised_status == expected


def test_loyalty_card_wallet_balance_required_fields():
    required_data = {}
    expected = {
        "updated_at": None,
        "current_display_value": None,
        "loyalty_currency_name": None,
        "prefix": None,
        "suffix": None,
        "current_value": None,
        "target_value": None,
    }
    serialised_status = LoyaltyCardWalletBalanceSerializer(**required_data)

    assert serialised_status == expected


def test_loyalty_card_wallet_balance_with_optionals(loyalty_card_balance_data):
    expected = {
        "updated_at": 1,
        "current_display_value": "you have 100 points",
        "loyalty_currency_name": "points",
        "prefix": "you have",
        "suffix": "points",
        "current_value": "10",
        "target_value": "100",
    }
    serialised_status = LoyaltyCardWalletBalanceSerializer(**loyalty_card_balance_data).dict()

    assert serialised_status == expected


def test_loyalty_card_wallet_transaction_required_fields(loyalty_card_transaction_data):
    required_data = {"id": loyalty_card_transaction_data["id"]}
    expected = {
        "id": "1232134",
        "timestamp": None,
        "description": None,
        "display_value": None,
    }
    serialised_status = LoyaltyCardWalletTransactionsSerializer(**required_data).dict()

    assert serialised_status == expected


def test_loyalty_card_wallet_transaction_with_optionals(loyalty_card_transaction_data):
    expected = {
        "id": "1232134",
        "timestamp": 1,
        "description": "Some description",
        "display_value": "Some value",
    }
    serialised_status = LoyaltyCardWalletTransactionsSerializer(**loyalty_card_transaction_data).dict()

    assert serialised_status == expected


def test_loyalty_card_wallet_voucher_required_fields(loyalty_card_voucher_data):
    required_data = {"state": loyalty_card_voucher_data["state"]}
    expected = {
        "state": "redeemed",
        "earn_type": None,
        "reward_text": None,
        "headline": None,
        "voucher_code": None,
        "barcode_type": None,
        "progress_display_text": None,
        "current_value": None,
        "target_value": None,
        "prefix": None,
        "suffix": None,
        "body_text": None,
        "terms_and_conditions": None,
        "issued_date": None,
        "expiry_date": None,
        "redeemed_date": None,
    }
    serialised_status = LoyaltyCardWalletVouchersSerializer(**required_data).dict()

    assert serialised_status == expected


def test_loyalty_card_wallet_voucher_with_optionals(loyalty_card_voucher_data):
    expected = {
        "state": "redeemed",
        "earn_type": "points",
        "reward_text": "get some points",
        "headline": "hello",
        "voucher_code": "yes",
        "barcode_type": 1,
        "progress_display_text": "this is how to progress",
        "current_value": "100",
        "target_value": "500",
        "prefix": "get some",
        "suffix": "points",
        "body_text": "here's some points",
        "terms_and_conditions": "http://some.url",
        "issued_date": "12/12/2012",
        "expiry_date": "13/12/2012",
        "redeemed_date": "12/12/2012",
    }
    serialised_status = LoyaltyCardWalletVouchersSerializer(**loyalty_card_voucher_data).dict()

    assert serialised_status == expected


def test_loyalty_card_wallet_voucher_type_casting(loyalty_card_voucher_data):
    loyalty_card_voucher_data["barcode_type"] = "1"
    loyalty_card_voucher_data["current_value"] = 100
    loyalty_card_voucher_data["target_value"] = 500

    serialised_status = LoyaltyCardWalletVouchersSerializer(**loyalty_card_voucher_data)

    assert isinstance(serialised_status.barcode_type, int)
    assert isinstance(serialised_status.current_value, str)
    assert isinstance(serialised_status.target_value, str)

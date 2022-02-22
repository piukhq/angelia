from tests.handlers.test_wallet_handler import expected_balance, expected_transactions, expected_vouchers
from tests.helpers.authenticated_request import get_authenticated_request


def test_empty_wallet(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_wallet_response")
    mocked_resp.return_value = {"joins": [], "loyalty_cards": [], "payment_accounts": []}
    resp = get_authenticated_request(path="/v2/wallet", method="GET")
    assert resp.json["joins"] == []
    assert resp.json["loyalty_cards"] == []
    assert resp.json["payment_accounts"] == []
    assert resp.status_code == 200


def test_loyalty_cards_in_wallet(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_wallet_response")
    loyalty_cards = [
        {
            "id": 11,
            "loyalty_plan_id": 1,
            "loyalty_plan_name": "My_Plan",
            "status": {"state": "authorised", "slug": None, "description": None},
            "balance": {"updated_at": None, "current_display_value": None},
            "transactions": [],
            "vouchers": [
                {
                    "state": "inprogress",
                    "headline": "Spend £7 or more to get a stamp. Collect 7 stamps to get a "
                    "Meal Voucher of up to £7 off your next meal.",
                    "code": None,
                    "barcode_type": 0,
                    "body_text": "",
                    "terms_and_conditions_url": "test.com",
                    "date_issued": None,
                    "expiry_date": None,
                    "date_redeemed": None,
                    "earn_type": "stamps",
                    "progress_display_text": "0/7 stamps",
                    "suffix": "stamps",
                    "prefix": None,
                    "current_value": "0",
                    "target_value": "7",
                    "reward_text": "Free Meal",
                }
            ],
            "card": {
                "barcode": "",
                "barcode_type": None,
                "card_number": "9511143200133540455516",
                "colour": "#78ce08",
                "text_colour": "#78ce10",
            },
            "images": [
                {
                    "id": 372,
                    "type": 0,
                    "url": "schemes/Iceland_dwPpkoM.jpg",
                    "description": "Iceland Hero Image",
                    "encoding": "jpg",
                }
            ],
            "pll_links": None,
        },
        {
            "id": 12,
            "images": [],
            "loyalty_plan_id": 2,
            "loyalty_plan_name": "Another_Plan",
            "status": {"state": "pending", "slug": "WALLET_ONLY", "description": "No authorisation provided"},
            "balance": {"updated_at": None, "current_display_value": None},
            "transactions": [],
            "vouchers": [],
            "card": {
                "barcode": "",
                "barcode_type": None,
                "card_number": "9511143200133540455526",
                "colour": "#78ce08",
                "text_colour": "#78ce10",
            },
            "pll_links": None,
        },
    ]

    join_cards = [
        {
            "id": 26550,
            "loyalty_plan_id": 105,
            "loyalty_plan_name": "Iceland Bonus Card",
            "status": {"state": "pending", "slug": None, "description": None},
            "images": [
                {
                    "id": 372,
                    "type": 0,
                    "url": "schemes/Iceland_dwPpkoM.jpg",
                    "description": "Iceland Hero Image",
                    "encoding": "jpg",
                }
            ],
        }
    ]
    mocked_resp.return_value = {"joins": join_cards, "loyalty_cards": loyalty_cards, "payment_accounts": []}
    resp = get_authenticated_request(path="/v2/wallet", method="GET")
    assert resp.json["joins"] == [
        {
            "loyalty_card_id": 26550,
            "loyalty_plan_id": 105,
            "loyalty_plan_name": "Iceland Bonus Card",
            "status": {"state": "pending", "slug": None, "description": None},
            "images": [
                {
                    "id": 372,
                    "type": 0,
                    "url": "schemes/Iceland_dwPpkoM.jpg",
                    "description": "Iceland Hero Image",
                    "encoding": "jpg",
                }
            ],
        }
    ]

    assert resp.json["loyalty_cards"] == [
        {
            "id": 11,
            "loyalty_plan_id": 1,
            "loyalty_plan_name": "My_Plan",
            "status": {"state": "authorised", "slug": None, "description": None},
            "balance": {
                "updated_at": None,
                "current_display_value": None,
                "loyalty_currency_name": None,
                "prefix": None,
                "suffix": None,
                "value": None,
            },
            "transactions": [],
            "vouchers": [
                {
                    "state": "inprogress",
                    "earn_type": "stamps",
                    "reward_text": "Free Meal",
                    "headline": "Spend £7 or more to get a stamp. Collect 7 stamps to get a Meal Voucher of "
                    "up to £7 off your next meal.",
                    "voucher_code": None,
                    "barcode_type": 0,
                    "progress_display_text": "0/7 stamps",
                    "suffix": "stamps",
                    "prefix": None,
                    "current_value": "0",
                    "target_value": "7",
                    "body_text": None,
                    "terms_and_conditions": "test.com",
                    "issued_date": None,
                    "expiry_date": None,
                    "redeemed_date": None,
                }
            ],
            "card": {
                "barcode": None,
                "barcode_type": None,
                "card_number": "9511143200133540455516",
                "colour": "#78ce08",
                "text_colour": "#78ce10",
            },
            "images": [
                {
                    "id": 372,
                    "type": 0,
                    "url": "schemes/Iceland_dwPpkoM.jpg",
                    "description": "Iceland Hero Image",
                    "encoding": "jpg",
                }
            ],
            "pll_links": [],
        },
        {
            "id": 12,
            "loyalty_plan_id": 2,
            "loyalty_plan_name": "Another_Plan",
            "images": [],
            "status": {"state": "pending", "slug": "WALLET_ONLY", "description": "No authorisation provided"},
            "balance": {
                "updated_at": None,
                "current_display_value": None,
                "loyalty_currency_name": None,
                "prefix": None,
                "suffix": None,
                "value": None,
            },
            "transactions": [],
            "vouchers": [],
            "card": {
                "barcode": None,
                "barcode_type": None,
                "card_number": "9511143200133540455526",
                "colour": "#78ce08",
                "text_colour": "#78ce10",
            },
            "pll_links": [],
        },
    ]

    assert resp.json["payment_accounts"] == []
    assert resp.status_code == 200


def test_loyalty_card_wallet_transactions(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_loyalty_card_transactions_response")
    mocked_resp.return_value = expected_transactions
    resp = get_authenticated_request(path="/v2/loyalty_cards/11/transactions", method="GET")
    assert resp.status_code == 200
    assert len(resp.json) == 1
    transactions = resp.json.get("transactions", [])
    assert len(transactions) == 5


def test_loyalty_card_wallet_vouchers(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_loyalty_card_vouchers_response")
    mocked_resp.return_value = expected_vouchers
    resp = get_authenticated_request(path="/v2/loyalty_cards/11/vouchers", method="GET")
    assert resp.status_code == 200
    assert len(resp.json) == 1
    vouchers = resp.json.get("vouchers", [])
    assert len(vouchers) == 4


def test_loyalty_card_wallet_balance(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_loyalty_card_balance_response")
    mocked_resp.return_value = expected_balance
    resp = get_authenticated_request(path="/v2/loyalty_cards/11/balance", method="GET")
    assert resp.status_code == 200
    assert len(resp.json) == 1
    balance = resp.json.get("balance", [])
    assert len(balance) == 6
    assert balance["updated_at"] == 1637323977
    assert balance["current_display_value"] == "3 stamps"

def test_wallet_loyalty_card_by_id(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_loyalty_card_by_id_response")

    loyalty_card = {
            "id": 12,
            "images": [],
            "loyalty_plan_id": 2,
            "loyalty_plan_name": "Another_Plan",
            "status": {"state": "pending", "slug": "WALLET_ONLY", "description": "No authorisation provided"},
            "balance": {"updated_at": None, "current_display_value": None},
            "transactions": [],
            "vouchers": [],
            "card": {
                "barcode": "",
                "barcode_type": None,
                "card_number": "9511143200133540455526",
                "colour": "#78ce08",
                "text_colour": "#78ce10",
            },
            "pll_links": None,
        }

    mocked_resp.return_value = loyalty_card
    resp = get_authenticated_request(path="/v2/wallet/loyalty_cards/12", method="GET")
    assert resp.json ==  {
            "id": 12,
            "loyalty_plan_id": 2,
            "loyalty_plan_name": "Another_Plan",
            "images": [],
            "status": {"state": "pending", "slug": "WALLET_ONLY", "description": "No authorisation provided"},
            "balance": {
                "updated_at": None,
                "current_display_value": None,
                "loyalty_currency_name": None,
                "prefix": None,
                "suffix": None,
                "value": None,
            },
            "transactions": [],
            "vouchers": [],
            "card": {
                "barcode": None,
                "barcode_type": None,
                "card_number": "9511143200133540455526",
                "colour": "#78ce08",
                "text_colour": "#78ce10",
            },
            "pll_links": [],
        }

    assert resp.status_code == 200



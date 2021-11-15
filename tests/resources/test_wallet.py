from tests.helpers.authenticated_request import get_authenticated_request


def test_empty_wallet(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_response_dict")
    mocked_resp.return_value = {"joins": [], "loyalty_cards": [], "payment_accounts": []}
    resp = get_authenticated_request(path="/v2/wallet", method="GET")
    assert resp.json["joins"] == []
    assert resp.json["loyalty_cards"] == []
    assert resp.json["payment_accounts"] == []
    assert resp.status_code == 200


def test_loyalty_cards_in_wallet(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_response_dict")
    loyalty_cards = [
        {
            "id": 11,
            "loyalty_plan_id": 1,
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
                    "reward_text": "Free Meal",
                }
            ],
            "card": {"barcode": "", "barcode_type": None, "card_number": "9511143200133540455516", "colour": "#78ce08"},
            "pll_links": None,
        },
        {
            "id": 12,
            "loyalty_plan_id": 2,
            "status": {"state": "pending", "slug": "WALLET_ONLY", "description": "No authorisation provided"},
            "balance": {"updated_at": None, "current_display_value": None},
            "transactions": [],
            "vouchers": [],
            "card": {"barcode": "", "barcode_type": None, "card_number": "9511143200133540455526", "colour": "#78ce08"},
            "pll_links": None,
        },
    ]
    mocked_resp.return_value = {"joins": [], "loyalty_cards": loyalty_cards, "payment_accounts": []}
    resp = get_authenticated_request(path="/v2/wallet", method="GET")
    assert resp.json["joins"] == []
    assert resp.json["loyalty_cards"] == [
        {
            "id": 11,
            "loyalty_plan_id": 1,
            "status": {"state": "authorised", "slug": None, "description": None},
            "balance": {"updated_at": None, "current_display_value": None},
            "transactions": [],
            "vouchers": [
                {
                    "state": "inprogress",
                    "earn_type": "stamps",
                    "reward_text": "Free Meal",
                    "headline": "Spend £7 or more to get a stamp. Collect 7 stamps to get a Meal Voucher of "
                    "up to £7 off your next meal.",
                    "voucher_code": None,
                    "barcode_type": "0",
                    "progress_display_text": "0/7 stamps",
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
            },
            "pll_links": [],
        },
        {
            "id": 12,
            "loyalty_plan_id": 2,
            "status": {"state": "pending", "slug": "WALLET_ONLY", "description": "No authorisation provided"},
            "balance": {"updated_at": None, "current_display_value": None},
            "transactions": [],
            "vouchers": [],
            "card": {
                "barcode": None,
                "barcode_type": None,
                "card_number": "9511143200133540455526",
                "colour": "#78ce08",
            },
            "pll_links": [],
        },
    ]

    assert resp.json["payment_accounts"] == []
    assert resp.status_code == 200

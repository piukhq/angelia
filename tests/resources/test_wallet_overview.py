from tests.helpers.authenticated_request import get_authenticated_request


def test_empty_wallet_overview(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_overview_wallet_response")
    mocked_resp.return_value = {"joins": [], "loyalty_cards": [], "payment_accounts": []}
    resp = get_authenticated_request(path="/v2/wallet_overview", method="GET")
    assert resp.json["joins"] == []
    assert resp.json["loyalty_cards"] == []
    assert resp.json["payment_accounts"] == []
    assert resp.status_code == 200


def test_loyalty_cards_in_wallet_overview(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_overview_wallet_response")
    loyalty_cards = [
        {
            "id": 26550,
            "loyalty_plan_id": 105,
            "loyalty_plan_name": "Iceland Bonus Card",
            "is_fully_pll_linked": False,
            "pll_linked_payment_accounts": 0,
            "total_payment_accounts": 1,
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
            "balance": {
                "updated_at": 1635930532,
                "current_display_value": "£1480",
                "loyalty_currency_name": "GBP",
                "prefix": "£",
                "suffix": None,
                "current_value": "1480",
                "target_value": None,
            },
            "card": {
                "barcode": "1000001447727",
                "barcode_type": 7,
                "card_number": "1000001447727",
                "colour": "#000000",
                "text_colour": None,
            },
            "reward_available": True,
        }
    ]
    join_cards = [
        {
            "id": 26550,
            "loyalty_plan_id": 105,
            "loyalty_plan_name": "Iceland Bonus Card",
            "status": {"state": "pending", "slug": None, "description": None},
            "card": {
                "barcode": None,
                "barcode_type": None,
                "card_number": None,
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
        }
    ]

    mocked_resp.return_value = {"joins": join_cards, "loyalty_cards": loyalty_cards, "payment_accounts": []}
    resp = get_authenticated_request(path="/v2/wallet_overview", method="GET")
    join_cards[0]["loyalty_card_id"] = join_cards[0].pop("id")
    assert resp.status_code == 200
    assert resp.json["joins"] == join_cards
    assert resp.json["loyalty_cards"] == loyalty_cards
    assert resp.json["payment_accounts"] == []


def test_loyalty_cards_no_image_in_wallet_overview(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_overview_wallet_response")
    loyalty_cards = [
        {
            "id": 26550,
            "loyalty_plan_id": 105,
            "loyalty_plan_name": "Iceland Bonus Card",
            "is_fully_pll_linked": True,
            "pll_linked_payment_accounts": 1,
            "total_payment_accounts": 1,
            "status": {"state": "pending", "slug": None, "description": None},
            "images": [],
            "balance": {
                "updated_at": 1635930532,
                "current_display_value": "£1480",
                "loyalty_currency_name": "GBP",
                "prefix": "£",
                "suffix": None,
                "current_value": "1480",
                "target_value": None,
            },
            "card": {
                "barcode": "1000001447727",
                "barcode_type": 7,
                "card_number": "1000001447727",
                "colour": "#000000",
                "text_colour": None,
            },
            "reward_available": True,
        }
    ]
    mocked_resp.return_value = {"joins": [], "loyalty_cards": loyalty_cards, "payment_accounts": []}
    resp = get_authenticated_request(path="/v2/wallet_overview", method="GET")
    assert resp.status_code == 200
    assert resp.json["joins"] == []
    assert resp.json["loyalty_cards"] == loyalty_cards
    assert resp.json["payment_accounts"] == []


def test_payment_cards_in_wallet_overview(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_overview_wallet_response")
    payment_cards = [
        {
            "id": 24958,
            "provider": "Provider",
            "status": 0,
            "issuer": "HSBC",
            "card_nickname": "My Mastercard",
            "name_on_card": "Jeff Bloggs3",
            "expiry_month": 9,
            "expiry_year": 23,
            "type": "debit",
            "currency_code": "GBP",
            "country": "GB",
            "last_four_digits": "9876",
            "images": [
                {
                    "id": 7,
                    "type": 0,
                    "url": "schemes/Visa-Payment_DWQzhta.png",
                    "description": "Visa Card Image",
                    "encoding": "png",
                }
            ],
        }
    ]
    mocked_resp.return_value = {"joins": [], "loyalty_cards": [], "payment_accounts": payment_cards}
    resp = get_authenticated_request(path="/v2/wallet_overview", method="GET")
    assert resp.status_code == 200
    assert resp.json["joins"] == []
    assert resp.json["loyalty_cards"] == []
    payment_cards[0]["status"] = "pending"
    payment_cards[0]["expiry_month"] = "9"
    payment_cards[0]["expiry_year"] = "23"
    assert resp.json["payment_accounts"] == payment_cards

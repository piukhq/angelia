from tests.helpers.authenticated_request import get_authenticated_request


def test_empty_wallet(mocker):
    mocked_resp = mocker.patch("app.handlers.wallet.WalletHandler.get_response_dict")
    mocked_resp.return_value = {"joins": [], "loyalty_cards": [], "payment_accounts": []}
    resp = get_authenticated_request(path="/v2/wallet", method="GET")
    assert resp.json["joins"] == []
    assert resp.json["loyalty_cards"] == []
    assert resp.json["payment_accounts"] == []

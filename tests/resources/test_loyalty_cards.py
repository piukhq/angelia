from unittest.mock import patch

from falcon import HTTP_200, HTTP_201, HTTP_202

from tests.helpers.authenticated_request import get_authenticated_request

req_data = {
    "loyalty_plan": 77,
    "account": {"add_fields": [{"credential_slug": "barcode", "value": "9511143200133540455525"}]},
}

auth_req_data = {
    "loyalty_plan": 718,
    "account": {
        "add_fields": [{"credential_slug": "card_number", "value": "663344667788"}],
        "authorise_fields": [{"credential_slug": "password", "value": "password123"}],
    },
}


@patch("app.resources.loyalty_cards.LoyaltyCardHandler")
def test_add_response_created(mock_handler):
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.add_card_to_wallet.return_value = True
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=req_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_201


@patch("app.resources.loyalty_cards.LoyaltyCardHandler")
def test_add_response_returned_or_linked(mock_handler):
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.add_card_to_wallet.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=req_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200


@patch("app.resources.loyalty_cards.LoyaltyCardHandler")
def test_add_and_auth_response_created(mock_handler):
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.add_auth_card.return_value = True
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=auth_req_data,
        method="POST",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_202


@patch("app.resources.loyalty_cards.LoyaltyCardHandler")
def test_add_and_auth_response_returned_or_linked(mock_handler):
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.add_auth_card.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=auth_req_data,
        method="POST",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_200
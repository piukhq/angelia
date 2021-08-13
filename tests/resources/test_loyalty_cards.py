from unittest.mock import patch

from falcon import HTTP_200, HTTP_201

from tests.helpers.authenticated_request import get_authenticated_request

req_data = {
    "loyalty_plan": 77,
    "account": {"add_fields": [{"credential_slug": "barcode", "value": "9511143200133540455525"}]},
}


@patch("app.resources.loyalty_cards.LoyaltyCardHandler.add_card", return_value=(True, 1))
def test_add_response_created(mock_add_card):
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=req_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_201


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.add_card", return_value=(False, 1))
def test_add_response_returned_or_linked(mock_add_card):
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=req_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200

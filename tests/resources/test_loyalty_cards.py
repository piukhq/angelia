from falcon import (
    HTTP_201,
    HTTP_200,
    testing,
)

from unittest.mock import patch
from tests.authentication.test_access_token import create_bearer_token

from app.api import app

client = testing.TestClient(app.create_app())

req_data = {
    "loyalty_plan": 77,
    "account": {"add_fields": [{"credential_slug": "barcode", "value": "9511143200133540455525"}]},
}


def get_authenticated_request(method, json, path, user_id=1, channel="com.test.channel"):
    auth_dict = {"test-secret-1": "secret_1"}
    with patch.dict("app.api.auth.vault_access_secret", auth_dict):
        auth_token = create_bearer_token("test-secret-1", auth_dict, user_id, channel)
        resp = client.simulate_request(path=path, json=json, headers={"Authorization": auth_token}, method=method)

        return resp


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

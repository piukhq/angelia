from falcon import (
    testing,
)

from unittest.mock import patch

from app.api import app

client = testing.TestClient(app.create_app())

req_data = {
    "loyalty_plan": 77,
    "account": {"add_fields": [{"credential_slug": "barcode", "value": "9511143200133540455525"}]},
}


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.add_card", return_value=True)
def test_add_response_created(mock_add_card):

    resp = client.simulate_post("/v2/loyalty_cards/add", json=req_data)
    assert resp.status == 201


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.add_card", return_value=False)
def test_add_response_returned_or_linked(mock_add_card):

    resp = client.simulate_post("/v2/loyalty_cards/add", json=req_data)
    assert resp.status == 200

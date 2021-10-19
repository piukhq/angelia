from unittest.mock import patch

from falcon import HTTP_200, HTTP_404

from tests.helpers.authenticated_request import get_authenticated_request

journey_fields_resp_data = {
    "loyalty_plan_id": 105,
    "add_fields": {
        "credentials": [
            {
                "order": 12,
                "display_label": "display label",
                "validation": "'*V'",
                "description": "here is a description",
                "credential_slug": "slug",
                "type": "type",
                "is_sensitive": False,
            }
        ]
    },
}

all_plans_resp_data = [{}]


@patch("app.resources.loyalty_plans.LoyaltyPlanHandler.get_journey_fields")
def test_get_plan_journey_fields(mock_get_journey_fields):
    mock_get_journey_fields.return_value = journey_fields_resp_data
    resp = get_authenticated_request(
        path="/v2/loyalty_plans/105/journey_fields", method="GET", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200


@patch("app.resources.loyalty_plans.LoyaltyPlanHandler.get_journey_fields")
def test_get_plan_journey_fields_user_id_wrong_type(mock_get_journey_fields):
    mock_get_journey_fields.return_value = journey_fields_resp_data
    resp = get_authenticated_request(
        path="/v2/loyalty_plans/hello/journey_fields", json="", method="GET", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_404


@patch("app.resources.loyalty_plans.LoyaltyPlansHandler.get_all_plans")
def test_get_all_plans(mock_get_all_plans):
    resp = get_authenticated_request(path="/v2/loyalty_plans", method="GET", user_id=1, channel="com.test.channel")
    assert mock_get_all_plans.called
    assert resp.status == HTTP_200

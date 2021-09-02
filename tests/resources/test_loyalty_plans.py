from unittest.mock import patch

from falcon import HTTP_200, HTTP_404

from tests.helpers.authenticated_request import get_authenticated_request

resp_data = {
    "id": 105,
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


@patch("app.resources.loyalty_plans.LoyaltyPlanHandler.get_journey_fields")
def test_get_plan_journey_fields(mock_get_journey_fields):
    mock_get_journey_fields.return_value = resp_data
    resp = get_authenticated_request(
        path="/v2/loyalty_plans/105/journey_fields", json="", method="GET", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200


@patch("app.resources.loyalty_plans.LoyaltyPlanHandler.get_journey_fields")
def test_get_plan_journey_fields_user_id_wrong_type(mock_get_journey_fields):
    mock_get_journey_fields.return_value = resp_data
    resp = get_authenticated_request(
        path="/v2/loyalty_plans/hello/journey_fields", json="", method="GET", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_404
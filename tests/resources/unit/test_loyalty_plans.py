from unittest.mock import MagicMock, patch

from falcon import HTTP_200, HTTP_404

from angelia.hermes.models import Scheme
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
                "is_scannable": False,
                "is_optional": False,
            }
        ]
    },
}


@patch("angelia.resources.loyalty_plans.LoyaltyPlanHandler.get_journey_fields")
def test_get_plan_journey_fields(mock_get_journey_fields: MagicMock) -> None:
    mock_get_journey_fields.return_value = journey_fields_resp_data
    resp = get_authenticated_request(
        path="/v2/loyalty_plans/105/journey_fields", method="GET", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200


@patch("angelia.resources.loyalty_plans.LoyaltyPlanHandler.get_journey_fields")
def test_get_plan_journey_fields_user_id_wrong_type(mock_get_journey_fields: MagicMock) -> None:
    mock_get_journey_fields.return_value = journey_fields_resp_data
    resp = get_authenticated_request(
        path="/v2/loyalty_plans/hello/journey_fields", json="", method="GET", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_404


@patch("angelia.resources.loyalty_plans.LoyaltyPlanHandler.get_plan")
def test_get_plan(mock_get_plan: MagicMock, loyalty_plan: Scheme) -> None:
    mock_get_plan.return_value = loyalty_plan
    resp = get_authenticated_request(path="/v2/loyalty_plans/1", method="GET", user_id=1, channel="com.test.channel")
    assert mock_get_plan.called
    assert resp.status == HTTP_200


@patch("angelia.resources.loyalty_plans.LoyaltyPlanHandler.get_plan_details")
def test_get_plan_details(mock_get_plan_details: MagicMock, loyalty_plan_details: dict) -> None:
    mock_get_plan_details.return_value = loyalty_plan_details
    resp = get_authenticated_request(
        path="/v2/loyalty_plans/1/plan_details", method="GET", user_id=1, channel="com.test.channel"
    )
    assert mock_get_plan_details.called
    assert resp.status == HTTP_200


@patch("angelia.resources.loyalty_plans.LoyaltyPlansHandler.get_all_plans")
def test_get_all_plans(mock_get_all_plans: MagicMock, loyalty_plan: Scheme) -> None:
    mock_get_all_plans.return_value = [loyalty_plan]
    resp = get_authenticated_request(path="/v2/loyalty_plans", method="GET", user_id=1, channel="com.test.channel")
    assert mock_get_all_plans.called
    assert resp.status == HTTP_200


@patch("angelia.resources.loyalty_plans.LoyaltyPlansHandler.get_all_plans_overview")
def test_get_all_plans_overview(mock_get_all_plans_overview: MagicMock, loyalty_plan_overview: dict) -> None:
    mock_get_all_plans_overview.return_value = [loyalty_plan_overview]
    resp = get_authenticated_request(
        path="/v2/loyalty_plans_overview", method="GET", user_id=1, channel="com.test.channel"
    )
    assert mock_get_all_plans_overview.called
    assert resp.status == HTTP_200

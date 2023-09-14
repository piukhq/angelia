import typing
from unittest.mock import call, patch

import falcon
import pytest
from sqlalchemy.future import select

from app.hermes.models import (
    Channel,
    Consent,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    ThirdPartyConsentLink,
    User,
)
from app.lib.loyalty_card import OriginatingJourney
from tests.factories import LoyaltyPlanQuestionFactory
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session


@pytest.mark.parametrize(
    "consents,http_status",
    [
        (
            [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
            ],
            falcon.HTTP_202,
        ),
        (
            [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
                {"consent_slug": "Consent_UNKNOWN", "value": "oops"},
            ],
            falcon.HTTP_422,
        ),
    ],
    ids=("CONSENTS_OK", "UNKNOWN_CONSENT"),
)
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_join(
    mock_send_message_to_hermes: "MagicMock",
    consents: list[dict],
    http_status: str,
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    setup_consents: typing.Callable[[dict, Channel], list[ThirdPartyConsentLink]],
) -> None:
    """Tests that user is successfully linked to a newly created Scheme Account (JOIN)

    Also tests that 422 is returned for extra unknown consents
    """

    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    db_session.flush()
    setup_questions(loyalty_plan)
    setup_consents(loyalty_plan, channel)
    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "join_fields": {
                "credentials": [
                    {"credential_slug": "postcode", "value": "007"},
                    {"credential_slug": "last_name", "value": "Bond"},
                ],
                "consents": consents,
            },
        },
    }

    # adding an optional credential question to check that not providing an answer for it still result in success.
    LoyaltyPlanQuestionFactory(
        type="random",
        label="Random",
        scheme_id=loyalty_plan.id,
        is_optional=True,
        register_field=True,
        enrol_field=True,
    )

    db_session.commit()

    assert not db_session.execute(select(SchemeAccount)).scalar_one_or_none()

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/join",
        json=payload,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == http_status

    if http_status == falcon.HTTP_422:
        assert resp.json == {
            "error_message": "Could not validate fields",
            "error_slug": "FIELD_VALIDATION_ERROR",
        }
        mock_send_message_to_hermes.assert_not_called()

    if http_status == falcon.HTTP_202:
        loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one_or_none()
        assert loyalty_card
        assert resp.json == {"id": loyalty_card.id}

        card = db_session.execute(select(SchemeAccount)).scalar_one_or_none()
        assert card

        link = db_session.execute(
            select(SchemeAccountUserAssociation).where(
                SchemeAccountUserAssociation.scheme_account_id == card.id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
        ).scalar_one_or_none()
        consent_id = db_session.execute(select(Consent.id).where(Consent.slug == "Consent_2")).scalar_one_or_none()

        assert link
        assert card.originating_journey == OriginatingJourney.JOIN
        assert mock_send_message_to_hermes.mock_calls == [
            call(
                "loyalty_card_join",
                {
                    "loyalty_plan_id": loyalty_plan_id,
                    "loyalty_card_id": card.id,
                    "entry_id": link.id,
                    "user_id": user_id,
                    "channel_slug": "com.test.channel",
                    "journey": "JOIN",
                    "auto_link": True,
                    "join_fields": [
                        {"credential_slug": "postcode", "value": "007"},
                        {"credential_slug": "last_name", "value": "bond"},
                    ],
                    "consents": [{"id": consent_id, "value": "GU554JG"}],
                },
            )
        ]


def test_on_post_join_incorrect_payload_422() -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/join", json={"dead": "beef"}, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_422
    assert resp.json["error_message"] == "Could not validate fields"
    assert resp.json["error_slug"] == "FIELD_VALIDATION_ERROR"
    assert "extra keys not allowed @ data['dead']" in resp.json["fields"]
    assert "required key not provided @ data['account']" in resp.json["fields"]
    assert "required key not provided @ data['loyalty_plan_id']" in resp.json["fields"]


def test_on_post_join_malformed_payload_400() -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/join", body=b"\xf0\x9f\x92\xa9", method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_400
    assert resp.json == {
        "error_message": "Invalid JSON",
        "error_slug": "MALFORMED_REQUEST",
    }

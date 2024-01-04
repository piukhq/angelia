import typing
from unittest.mock import call, patch

import falcon
import pytest
from sqlalchemy.future import select

from app.handlers.loyalty_card import JOIN, LoyaltyCardHandler
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
from tests.factories import (
    LoyaltyCardFactory,
    LoyaltyCardStatus,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanQuestionFactory,
)
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
def test_on_put_join(
    mock_send_message_to_hermes: "MagicMock",
    consents: list[dict],
    http_status: str,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """
    Tests that an update on a failed join journey is successfully concluded in Angelia

    Also tests that 422 is returned for extra unknown consents
    """
    answer_fields = {
        "join_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
                {"credential_slug": "last_name", "value": "Bond"},
            ],
            "consents": [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
            ],
        },
    }
    loyalty_card_handler, loyalty_plan, setup_questions, channel, user, _ = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=JOIN
    )
    loyalty_plan_id, user_id = loyalty_plan.id, user.id

    # adding an optional credential question to check that not providing an answer for it still result in success.
    LoyaltyPlanQuestionFactory(
        type="random",
        label="Random",
        scheme_id=loyalty_plan_id,
        is_optional=True,
        register_field=True,
        enrol_field=True,
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.flush()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user_id,
        link_status=LoyaltyCardStatus.JOIN_ERROR,
    )
    db_session.flush()

    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.link_to_user = user_asc
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

    db_session.commit()

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{new_loyalty_card.id}/join",
        json=payload,
        method="PUT",
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
        link = (
            db_session.query(SchemeAccountUserAssociation)
            .filter(
                SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
            .all()
        )
        assert link[0].link_status == LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS
        assert mock_send_message_to_hermes.called is True
        assert mock_send_message_to_hermes.call_args[0][0] == "loyalty_card_join"

        loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one_or_none()
        assert loyalty_card
        assert resp.json == {"id": loyalty_card.id}
        consent_id = db_session.execute(select(Consent.id).where(Consent.slug == "Consent_2")).scalar_one_or_none()
        assert mock_send_message_to_hermes.mock_calls == [
            call(
                "loyalty_card_join",
                {
                    "loyalty_plan_id": loyalty_plan_id,
                    "loyalty_card_id": loyalty_card.id,
                    "entry_id": link[0].id,
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


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_join_in_pending_state(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Tests that an update on a failed join journey fails when card is in a Join Pending state"""

    answer_fields = {
        "join_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
                {"credential_slug": "last_name", "value": "Bond"},
            ],
            "consents": [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
            ],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user, _ = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=JOIN
    )
    loyalty_plan_id, user_id = loyalty_plan.id, user.id

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.flush()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
    )
    db_session.flush()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "join_fields": {
                "credentials": [
                    {"credential_slug": "postcode", "value": "007"},
                    {"credential_slug": "last_name", "value": "Bond"},
                ],
                "consents": answer_fields["join_fields"]["consents"],
            },
        },
    }

    db_session.commit()

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{new_loyalty_card.id}/join",
        json=payload,
        method="PUT",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "The Join cannot be updated while it is in Progress.",
        "error_slug": "JOIN_IN_PROGRESS",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_put_join_in_non_failed_state(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Tests that an update on a failed join journey fails when card is in an Active state"""

    answer_fields = {
        "join_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
                {"credential_slug": "last_name", "value": "Bond"},
            ],
            "consents": [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
            ],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user, consents = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=JOIN
    )
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.flush()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id, user_id=user.id, link_status=LoyaltyCardStatus.ACTIVE
    )
    db_session.flush()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "join_fields": {
                "credentials": [
                    {"credential_slug": "postcode", "value": "007"},
                    {"credential_slug": "last_name", "value": "Bond"},
                ],
                "consents": answer_fields["join_fields"]["consents"],
            },
        },
    }

    db_session.commit()

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{new_loyalty_card.id}/join",
        json=payload,
        method="PUT",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "The Join can only be updated from a failed state.",
        "error_slug": "JOIN_NOT_IN_FAILED_STATE",
    }
    mock_send_message_to_hermes.assert_not_called()


@pytest.mark.parametrize(
    "expected_resp,http_status,link_status",
    [
        (
            None,
            falcon.HTTP_200,
            LoyaltyCardStatus.JOIN_ERROR,
        ),
        (
            {
                "error_message": "Loyalty card cannot be deleted until the Join process has completed",
                "error_slug": "JOIN_IN_PROGRESS",
            },
            falcon.HTTP_409,
            LoyaltyCardStatus.JOIN_IN_PROGRESS,
        ),
        (
            {"error_message": "Could not process request due to a conflict", "error_slug": "CONFLICT"},
            falcon.HTTP_409,
            LoyaltyCardStatus.ACTIVE,
        ),
        (
            {"error_message": "Could not find this account or card", "error_slug": "RESOURCE_NOT_FOUND"},
            falcon.HTTP_404,
            LoyaltyCardStatus.JOIN_ERROR,
        ),
    ],
    ids=("SUCCESS_DELETE", "JOIN_IN_PROGRESS", "ACTIVE_ACCOUNT", "RESOURCE_NOT_FOUND"),
)
def test_on_delete_join(
    expected_resp: dict | None,
    http_status: str,
    link_status: str,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Test that a delete join journey is successfully concluded in Angelia"""

    loyalty_card_handler, loyalty_plan, questions, channel, user, consents = setup_loyalty_card_handler()
    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.flush()

    new_loyalty_card_id, user_id = new_loyalty_card.id, user.id
    if http_status == falcon.HTTP_404:
        new_loyalty_card_id = new_loyalty_card_id + 1

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=link_status,
    )
    db_session.flush()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card_id
    db_session.commit()

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{new_loyalty_card_id}/join",
        method="DELETE",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == http_status
    if http_status == falcon.HTTP_200:
        updated_scheme_account = db_session.execute(
            select(SchemeAccount).where(SchemeAccount.id == new_loyalty_card_id)
        ).scalar_one_or_none()
        link = (
            db_session.query(SchemeAccountUserAssociation)
            .filter(
                SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
            .all()
        )
        assert updated_scheme_account.is_deleted
        assert not link
    else:
        assert resp.json == expected_resp

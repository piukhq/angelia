import typing
from unittest.mock import MagicMock, patch

import falcon
from sqlalchemy import func, select

from angelia.hermes.models import (
    Channel,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    User,
)
from tests.factories import UserFactory
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_req_data: dict,
) -> None:
    """Tests that user is successfully linked to a newly created Scheme Account"""

    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    user_id, loyalty_plan_id = (
        user.id,
        loyalty_plan.id,
    )  # middleware closes the session and detaches this object from it
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    req_data = add_req_data.copy()

    req_data["loyalty_plan_id"] = loyalty_plan.id
    channel = "com.test.channel"
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=req_data, method="POST", user_id=user_id, channel=channel
    )

    assert resp.status == falcon.HTTP_201
    scheme_account = db_session.execute(select(SchemeAccount)).scalar_one()
    assert scheme_account.card_number == req_data["account"]["add_fields"]["credentials"][0]["value"]
    assert (
        db_session.execute(
            select(func.count())
            .select_from(SchemeAccountUserAssociation)
            .where(
                SchemeAccountUserAssociation.scheme_account_id == scheme_account.id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
        ).scalar()
        == 1
    )
    mock_send_message_to_hermes.assert_called_once_with(
        "loyalty_card_add",
        {
            "add_fields": [
                {
                    "credential_slug": "card_number",
                    "value": req_data["account"]["add_fields"]["credentials"][0]["value"],
                }
            ],
            "auto_link": True,
            "channel_slug": channel,
            "entry_id": scheme_account.scheme_account_user_associations[0].id,
            "journey": "ADD",
            "loyalty_card_id": scheme_account.id,
            "loyalty_plan_id": loyalty_plan_id,
            "user_id": user_id,
        },
    )


def test_on_post_add_incorrect_payload_422(db_session: "Session") -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json={"dead": "beef"}, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_422
    assert resp.json["error_message"] == "Could not validate fields"
    assert resp.json["error_slug"] == "FIELD_VALIDATION_ERROR"
    assert "extra keys not allowed @ data['dead']" in resp.json["fields"]
    assert "required key not provided @ data['account']" in resp.json["fields"]
    assert "required key not provided @ data['loyalty_plan_id']" in resp.json["fields"]


def test_on_post_add_malformed_payload_400(db_session: "Session") -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", body=b"\xf0\x9f\x92\xa9", method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_400
    assert resp.json == {
        "error_message": "Invalid JSON",
        "error_slug": "MALFORMED_REQUEST",
    }


def test_on_post_add_conflict_409(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_req_data: dict,
) -> None:
    """Tests that existing loyalty card is returned when there is an existing LoyaltyCard and link to this user (ADD)"""
    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    user_id = user.id  # middleware closes the session and detaches this object from it
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    req_data = add_req_data.copy()

    req_data["loyalty_plan_id"] = loyalty_plan.id
    for expected_status in (falcon.HTTP_201, falcon.HTTP_409):
        resp = get_authenticated_request(
            path="/v2/loyalty_cards/add", json=req_data, method="POST", user_id=user_id, channel="com.test.channel"
        )

        assert resp.status == expected_status

    assert resp.json == {
        "error_message": "Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/register to register this card.",
        "error_slug": "ALREADY_ADDED",
    }


def test_on_post_add_card_already_linked_to_other_user(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_req_data: dict,
) -> None:
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user (ADD)"""
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id = loyalty_plan.id
    user_id = user.id  # middleware closes the session and detaches this object from it
    other_user = UserFactory(client=channel.client_application)
    db_session.flush()
    other_user_id = other_user.id

    setup_questions(loyalty_plan)
    db_session.commit()

    req_data = add_req_data.copy()
    req_data["loyalty_plan_id"] = loyalty_plan.id

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=req_data, method="POST", user_id=user_id, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_201
    link_id = db_session.execute(
        select(SchemeAccount.id).where(
            SchemeAccount.card_number == req_data["account"]["add_fields"]["credentials"][0]["value"],
            SchemeAccount.scheme_id == loyalty_plan_id,
        )
    ).scalar_one()

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=req_data, method="POST", user_id=other_user_id, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_200
    assert resp.json == {"id": link_id}

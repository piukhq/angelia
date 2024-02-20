import typing
from unittest.mock import MagicMock, call, patch

import falcon
import pytest
from sqlalchemy import func, select

from angelia.api.helpers.vault import AESKeyNames
from angelia.hermes.models import (
    Channel,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    User,
)
from angelia.lib.encryption import AESCipher
from angelia.lib.loyalty_card import LoyaltyCardStatus, OriginatingJourney
from tests.factories import (
    LoyaltyCardAnswerFactory,
    LoyaltyCardFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanQuestionFactory,
    UserFactory,
)
from tests.helpers.authenticated_request import get_authenticated_request
from tests.helpers.local_vault import set_vault_cache

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_auth(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_and_auth_req_data: dict,
) -> None:
    """Tests that user is successfully linked to a newly created Scheme Account (ADD_AND_AUTH)"""
    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    user_id, loyalty_plan_id = (
        user.id,
        loyalty_plan.id,
    )  # middleware closes the session and detaches this object from it
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    req_data = add_and_auth_req_data.copy()

    req_data["loyalty_plan_id"] = loyalty_plan.id
    channel = "com.test.channel"
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise", json=req_data, method="POST", user_id=user_id, channel=channel
    )

    loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one()

    assert resp.status == falcon.HTTP_202
    assert loyalty_card.card_number == req_data["account"]["add_fields"]["credentials"][0]["value"]
    assert loyalty_card.originating_journey == OriginatingJourney.ADD
    assert (
        db_session.execute(
            select(func.count())
            .select_from(SchemeAccountUserAssociation)
            .where(
                SchemeAccountUserAssociation.scheme_account_id == loyalty_card.id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
        ).scalar()
        == 1
    )
    assert mock_send_message_to_hermes.call_count == 2
    mock_send_message_to_hermes.assert_has_calls(
        [
            call(
                "add_auth_request_event",
                {
                    "auto_link": True,
                    "channel_slug": channel,
                    "entry_id": loyalty_card.scheme_account_user_associations[0].id,
                    "journey": "ADD_AND_AUTH",
                    "loyalty_card_id": loyalty_card.id,
                    "loyalty_plan_id": loyalty_plan_id,
                    "user_id": user_id,
                },
            ),
            call(
                "loyalty_card_add_auth",
                {
                    "authorise_fields": [
                        {
                            "credential_slug": "email",
                            "value": req_data["account"]["authorise_fields"]["credentials"][0]["value"],
                        },
                        {
                            "credential_slug": "password",
                            "value": req_data["account"]["authorise_fields"]["credentials"][1]["value"],
                        },
                    ],
                    "add_fields": [
                        {
                            "credential_slug": "card_number",
                            "value": req_data["account"]["add_fields"]["credentials"][0]["value"],
                        }
                    ],
                    "auto_link": True,
                    "channel_slug": channel,
                    "consents": [],
                    "entry_id": loyalty_card.scheme_account_user_associations[0].id,
                    "journey": "ADD_AND_AUTH",
                    "loyalty_card_id": loyalty_card.id,
                    "loyalty_plan_id": loyalty_plan_id,
                    "user_id": user_id,
                },
            ),
        ]
    )


def test_on_post_add_and_authorise_incorrect_payload_422(db_session: "Session") -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json={"dead": "beef"},
        method="POST",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_422
    assert resp.json["error_message"] == "Could not validate fields"
    assert resp.json["error_slug"] == "FIELD_VALIDATION_ERROR"
    assert "extra keys not allowed @ data['dead']" in resp.json["fields"]
    assert "required key not provided @ data['account']" in resp.json["fields"]
    assert "required key not provided @ data['loyalty_plan_id']" in resp.json["fields"]


def test_on_post_add_and_authorise_malformed_payload_400(db_session: "Session") -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        body=b"\xf0\x9f\x92\xa9",
        method="POST",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_400
    assert resp.json == {
        "error_message": "Invalid JSON",
        "error_slug": "MALFORMED_REQUEST",
    }


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_auth_authorisation_required(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_req_data: dict,
) -> None:
    """Tests that add_auth allows a single add field to authorise a card based on the loyalty plan
    authorisation_required flag."""
    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan.authorisation_required = False

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
        path="/v2/loyalty_cards/add_and_authorise", json=req_data, method="POST", user_id=user_id, channel=channel
    )

    loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one()

    assert resp.status == falcon.HTTP_202
    assert loyalty_card.card_number == req_data["account"]["add_fields"]["credentials"][0]["value"]
    assert loyalty_card.originating_journey == OriginatingJourney.ADD
    assert (
        db_session.execute(
            select(func.count())
            .select_from(SchemeAccountUserAssociation)
            .where(
                SchemeAccountUserAssociation.scheme_account_id == loyalty_card.id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
        ).scalar()
        == 1
    )
    assert mock_send_message_to_hermes.call_count == 2
    mock_send_message_to_hermes.assert_has_calls(
        [
            call(
                "add_auth_request_event",
                {
                    "auto_link": True,
                    "channel_slug": channel,
                    "entry_id": loyalty_card.scheme_account_user_associations[0].id,
                    "journey": "ADD_AND_AUTH",
                    "loyalty_card_id": loyalty_card.id,
                    "loyalty_plan_id": loyalty_plan_id,
                    "user_id": user_id,
                },
            ),
            call(
                "loyalty_card_add_auth",
                {
                    "authorise_fields": [],
                    "add_fields": [
                        {
                            "credential_slug": "card_number",
                            "value": req_data["account"]["add_fields"]["credentials"][0]["value"],
                        }
                    ],
                    "auto_link": True,
                    "channel_slug": channel,
                    "consents": [],
                    "entry_id": loyalty_card.scheme_account_user_associations[0].id,
                    "journey": "ADD_AND_AUTH",
                    "loyalty_card_id": loyalty_card.id,
                    "loyalty_plan_id": loyalty_plan_id,
                    "user_id": user_id,
                },
            ),
        ]
    )


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_auth_authorisation_required_validation_error(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_req_data: dict,
) -> None:
    """
    Tests that add_auth raises an error when a single add field is provided for authorisation for a loyalty
    plan that requires authorisation.
    """
    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan.authorisation_required = True

    user_id = user.id  # middleware closes the session and detaches this object from it
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    req_data = add_req_data.copy()

    req_data["loyalty_plan_id"] = loyalty_plan.id
    channel = "com.test.channel"
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise", json=req_data, method="POST", user_id=user_id, channel=channel
    )

    assert resp.status == falcon.HTTP_422
    assert resp.json == {
        "error_message": "Could not validate fields",
        "error_slug": "FIELD_VALIDATION_ERROR",
        "fields": "This loyalty plan requires authorise fields to use this endpoint",
    }
    assert mock_send_message_to_hermes.call_count == 0


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_authorise_existing_card_same_user(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_and_auth_req_data: dict,
) -> None:
    """Tests that existing loyalty card is returned when there is an existing (add and auth'ed) LoyaltyCard and link to
    this user (ADD_AND_AUTH)"""
    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    user_id = user.id  # middleware closes the session and detaches this object from it
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    req_data = add_and_auth_req_data.copy()

    req_data["loyalty_plan_id"] = loyalty_plan.id
    for _ in (1, 2):
        resp = get_authenticated_request(
            path="/v2/loyalty_cards/add_and_authorise",
            json=req_data,
            method="POST",
            user_id=user_id,
            channel="com.test.channel",
        )
        loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one()  # <- there should only be one of these
        assert resp.status == falcon.HTTP_202
        assert db_session.execute(
            select(SchemeAccountUserAssociation).where(
                SchemeAccountUserAssociation.scheme_account_id == loyalty_card.id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
        ).scalar_one_or_none()

        assert resp.json == {"id": loyalty_card.id}


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_authorise_existing_card_different_user(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_and_auth_req_data: dict,
) -> None:
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user (ADD_AND_AUTH)"""
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    other_user_id = user.id  # middleware closes the session and detaches this object from it
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    req_data = add_and_auth_req_data.copy()

    req_data["loyalty_plan_id"] = loyalty_plan.id
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=req_data,
        method="POST",
        user_id=other_user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_202

    channel = db_session.merge(channel)

    new_user = UserFactory(client=channel.client_application)
    db_session.commit()
    new_user_id = new_user.id

    assert not db_session.execute(
        select(SchemeAccountUserAssociation).where(
            SchemeAccountUserAssociation.user_id == new_user_id,
        )
    ).scalar_one_or_none()

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=req_data,
        method="POST",
        user_id=new_user_id,
        channel="com.test.channel",
    )
    new_user = db_session.merge(new_user)

    assert resp.status == falcon.HTTP_202
    loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one()  # <- there should only be one of these
    assert db_session.execute(
        select(SchemeAccountUserAssociation).where(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card.id,
            SchemeAccountUserAssociation.user_id == new_user_id,
        )
    ).scalar_one_or_none()
    assert resp.json == {"id": loyalty_card.id}


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_authorise_existing_card_different_user_with_active_link(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_and_auth_req_data: dict,
) -> None:
    """Tests expected route when a user tries to add a card which already exists in another wallet and is ACTIVE
    (ADD_AND_AUTH)"""
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    bundle_id = channel.bundle_id
    other_user_id, loyalty_plan_id = (
        user.id,
        loyalty_plan.id,
    )  # middleware closes the session and detaches this object from it
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    req_data = add_and_auth_req_data.copy()

    req_data["loyalty_plan_id"] = loyalty_plan.id
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=req_data,
        method="POST",
        user_id=other_user_id,
        channel="com.test.channel",
    )
    mock_send_message_to_hermes.reset_mock()

    assert resp.status == falcon.HTTP_202
    loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one()
    other_link = db_session.execute(
        select(SchemeAccountUserAssociation).where(
            SchemeAccountUserAssociation.user_id == other_user_id,
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card.id,
        )
    ).scalar_one_or_none()
    other_link.status = LoyaltyCardStatus.ACTIVE
    db_session.commit()

    channel = db_session.merge(channel)

    new_user = UserFactory(client=channel.client_application)
    db_session.commit()
    new_user_id = new_user.id

    assert not db_session.execute(
        select(SchemeAccountUserAssociation).where(
            SchemeAccountUserAssociation.user_id == new_user_id,
        )
    ).scalar_one_or_none()

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=req_data,
        method="POST",
        user_id=new_user_id,
        channel="com.test.channel",
    )
    new_user = db_session.merge(new_user)

    assert resp.status == falcon.HTTP_202
    loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one()  # <- there should still only be one of these
    entry_id = db_session.execute(
        select(SchemeAccountUserAssociation.id).where(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card.id,
            SchemeAccountUserAssociation.user_id == new_user_id,
        )
    ).scalar_one_or_none()
    assert resp.json == {"id": loyalty_card.id}
    mock_send_message_to_hermes.assert_has_calls(
        [
            call(
                "add_auth_request_event",
                {
                    "auto_link": True,
                    "channel_slug": bundle_id,
                    "entry_id": entry_id,
                    "journey": "ADD_AND_AUTH",
                    "loyalty_card_id": loyalty_card.id,
                    "loyalty_plan_id": loyalty_plan_id,
                    "user_id": new_user_id,
                },
            ),
            call(
                "loyalty_card_add_auth",
                {
                    "authorise_fields": [
                        {
                            "credential_slug": "email",
                            "value": req_data["account"]["authorise_fields"]["credentials"][0]["value"],
                        },
                        {
                            "credential_slug": "password",
                            "value": req_data["account"]["authorise_fields"]["credentials"][1]["value"],
                        },
                    ],
                    "add_fields": [
                        {
                            "credential_slug": "card_number",
                            "value": req_data["account"]["add_fields"]["credentials"][0]["value"],
                        }
                    ],
                    "auto_link": True,
                    "channel_slug": bundle_id,
                    "consents": [],
                    "entry_id": entry_id,
                    "journey": "ADD_AND_AUTH",
                    "loyalty_card_id": loyalty_card.id,
                    "loyalty_plan_id": loyalty_plan_id,
                    "user_id": new_user_id,
                },
            ),
        ]
    )
    assert mock_send_message_to_hermes.call_count == 2


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_authorise_existing_card_same_user_with_already_active_link_no_credentials_500(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_and_auth_req_data: dict,
) -> None:
    """Tests that existing loyalty card is returned when there is an existing (add and auth'ed) LoyaltyCard and link to
    this user (ADD_AND_AUTH)"""
    set_vault_cache(to_load=["aes-keys"])
    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    user_id = user.id
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    req_data = add_and_auth_req_data.copy()

    # setup
    req_data["loyalty_plan_id"] = loyalty_plan.id
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=req_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    loyalty_card = db_session.execute(select(SchemeAccount)).scalar_one()  # <- there should only be one of these

    assert resp.status == falcon.HTTP_202
    assert resp.json == {"id": loyalty_card.id}

    entry = db_session.execute(
        select(SchemeAccountUserAssociation).where(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card.id,
            SchemeAccountUserAssociation.user_id == user_id,
        )
    ).scalar_one()
    entry.link_status = LoyaltyCardStatus.ACTIVE
    db_session.commit()

    # test
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=req_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_500
    assert resp.json == {
        "error_message": "500 Internal Server Error",
        "error_slug": "INTERNAL_SERVER_ERROR",
    }

    assert mock_send_message_to_hermes.call_count == 2


@pytest.mark.parametrize("password", ["password123", "non_matching_password"])
@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_authorise_existing_card_same_user_with_credentials_409(
    mock_send_message_to_hermes: "MagicMock",
    password: str,
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    add_and_auth_req_data: dict,
) -> None:
    """
    Tests add_and_auth raises an error when attempting to add_and_auth an already added card.
    This will raise an error if a card with the given key credential already exists in the wallet,
    regardless of whether the existing auth credentials match or not.
    """
    set_vault_cache(to_load=["aes-keys"])
    card_number = "663344667788"
    email = "some@email.com"
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    user_id = user.id
    db_session.commit()
    req_data = add_and_auth_req_data.copy()

    # Question setup
    card_number_q = LoyaltyPlanQuestionFactory(
        scheme_id=loyalty_plan.id,
        type="card_number",
        label="Card Number",
        add_field=True,
        manual_question=True,
        order=3,
    )
    password_q = LoyaltyPlanQuestionFactory(
        scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True, order=9
    )

    email_q = LoyaltyPlanQuestionFactory(
        scheme_id=loyalty_plan.id, type="email", label="Email", auth_field=True, order=6
    )

    # Card and answer setup
    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)
    db_session.flush()

    association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    encrypted_pass = AESCipher(AESKeyNames.LOCAL_AES_KEY).encrypt(password).decode("utf-8")
    LoyaltyCardAnswerFactory(scheme_account_entry_id=association.id, question_id=card_number_q.id, answer=card_number)
    LoyaltyCardAnswerFactory(scheme_account_entry_id=association.id, question_id=password_q.id, answer=encrypted_pass)
    LoyaltyCardAnswerFactory(scheme_account_entry_id=association.id, question_id=email_q.id, answer=email)

    db_session.commit()
    # setup
    req_data["loyalty_plan_id"] = loyalty_plan.id
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=req_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "Card already authorised. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to modify "
        "authorisation credentials.",
        "error_slug": "ALREADY_AUTHORISED",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_authorise_after_trusted_add(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    trusted_add_req_data: dict,
    add_and_auth_req_data: dict,
) -> None:
    """
    Tests add_and_auth raises an error when attempting to add_and_auth a card which was already
    add via POST /trusted_add
    """
    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    card_number = "663344667788"
    user_id = user.id  # middleware closes the session and detaches this object from it
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.commit()
    add_auth_data = add_and_auth_req_data.copy()
    trusted_add_data = trusted_add_req_data.copy()
    add_auth_data["loyalty_plan_id"] = trusted_add_data["loyalty_plan_id"] = loyalty_plan.id

    add_auth_data["account"]["add_fields"]["credentials"][0]["value"] = trusted_add_data["account"]["add_fields"][
        "credentials"
    ][0]["value"] = card_number

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        json=trusted_add_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_201

    mock_send_message_to_hermes.reset_mock()

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=add_auth_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "Card already authorised. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to modify "
        "authorisation credentials.",
        "error_slug": "ALREADY_AUTHORISED",
    }
    assert mock_send_message_to_hermes.call_count == 0

import typing
from unittest.mock import MagicMock, call, patch

import falcon
import pytest
from sqlalchemy.future import select

from angelia.api.helpers.vault import AESKeyNames
from angelia.handlers.loyalty_card import LoyaltyCardHandler
from angelia.hermes.models import Channel, Scheme, SchemeAccountUserAssociation, SchemeCredentialQuestion, User
from angelia.lib.encryption import AESCipher
from angelia.lib.loyalty_card import LoyaltyCardStatus
from tests.factories import LoyaltyCardAnswerFactory, LoyaltyCardFactory, LoyaltyCardUserAssociationFactory, UserFactory
from tests.helpers.authenticated_request import get_authenticated_request
from tests.helpers.local_vault import set_vault_cache

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_authorise(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
) -> None:
    """
    Tests happy path for authorise journey.
    Existing card is in WALLET_ONLY state and is only linked to current user. No saved auth creds.
    """
    set_vault_cache(to_load=["aes-keys"])
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    db_session.flush()
    setup_questions(loyalty_plan)

    card_number = "9511143200133540455525"
    email = "whatever@binktest.com"
    payload = {
        "account": {
            "add_fields": {
                "credentials": [
                    {"credential_slug": "card_number", "value": card_number},
                ]
            },
            "authorise_fields": {
                "credentials": [
                    {"credential_slug": "email", "value": email},
                    {"credential_slug": "password", "value": "iLoveTests33"},
                ]
            },
        }
    }

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)
    db_session.flush()
    loyalty_card_id = new_loyalty_card.id

    entry = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )
    db_session.commit()
    entry_id = entry.id

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{new_loyalty_card.id}/authorise",
        json=payload,
        method="PUT",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_202
    assert mock_send_message_to_hermes.mock_calls == [
        call(
            "add_auth_request_event",
            {
                "loyalty_plan_id": loyalty_plan_id,
                "loyalty_card_id": loyalty_card_id,
                "entry_id": entry_id,
                "user_id": user_id,
                "channel_slug": "com.test.channel",
                "journey": "AUTH",
                "auto_link": True,
            },
        ),
        call(
            "loyalty_card_add_auth",
            {
                "loyalty_plan_id": loyalty_plan_id,
                "loyalty_card_id": loyalty_card_id,
                "entry_id": entry_id,
                "user_id": user_id,
                "channel_slug": "com.test.channel",
                "journey": "AUTH",
                "auto_link": True,
                "consents": [],
                "authorise_fields": [
                    {"credential_slug": "email", "value": email},
                    {"credential_slug": "password", "value": "iLoveTests33"},
                ],
                "add_fields": [{"credential_slug": "card_number", "value": card_number}],
            },
        ),
    ]


def test_on_put_authorise_incorrect_payload_422(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
) -> None:
    loyalty_plan, _channel, _user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="343243243243")
    db_session.flush()
    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{loyalty_card.id}/authorise",
        json={"dead": "beef"},
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_422
    assert resp.json["error_message"] == "Could not validate fields"
    assert resp.json["error_slug"] == "FIELD_VALIDATION_ERROR"
    assert "extra keys not allowed @ data['dead']" in resp.json["fields"]
    assert "required key not provided @ data['account']" in resp.json["fields"]


def test_on_put_authorise_malformed_payload_400(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
) -> None:
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="343243243243")
    db_session.flush()
    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{loyalty_card.id}/authorise",
        body=b"\xf0\x9f\x92\xa9",
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_400
    assert resp.json == {
        "error_message": "Invalid JSON",
        "error_slug": "MALFORMED_REQUEST",
    }


def test_on_put_authorise_404(db_session: "Session") -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/42/authorise",
        json={
            "account": {
                "add_fields": {
                    "credentials": [
                        {"credential_slug": "card_number", "value": "2342323423423"},
                    ]
                },
                "authorise_fields": {
                    "credentials": [
                        {"credential_slug": "email", "value": "whatever@binktest.com"},
                        {"credential_slug": "password", "value": "iLoveTests33"},
                    ]
                },
            }
        },
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_404
    assert resp.json == {
        "error_message": "Could not find this account or card",
        "error_slug": "RESOURCE_NOT_FOUND",
    }


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_authorise_wallet_only_linked_to_other_user_202(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
) -> None:
    """
    Tests authorising a card that is in WALLET_ONLY state and linked to another user.
    """
    set_vault_cache(to_load=["aes-keys"])
    card_number = "9511143200133540455525"
    email = "my_email@email.com"
    password = "iLoveTests33"
    payload = {
        "account": {
            "add_fields": {
                "credentials": [
                    {"credential_slug": "card_number", "value": card_number},
                ]
            },
            "authorise_fields": {
                "credentials": [
                    {"credential_slug": "email", "value": email},
                    {"credential_slug": "password", "value": password},
                ]
            },
        }
    }

    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    db_session.flush()
    setup_questions(loyalty_plan)

    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)
    existing_user = UserFactory(client=channel.client_application)
    db_session.commit()
    loyalty_card_id = loyalty_card_to_update.id

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=existing_user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    entry = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()
    entry_id = entry.id

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{loyalty_card_to_update.id}/authorise",
        json=payload,
        method="PUT",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == falcon.HTTP_202
    assert resp.json == {"id": loyalty_card_id}
    assert mock_send_message_to_hermes.mock_calls == [
        call(
            "add_auth_request_event",
            {
                "loyalty_plan_id": loyalty_plan_id,
                "loyalty_card_id": loyalty_card_id,
                "entry_id": entry_id,
                "user_id": user_id,
                "channel_slug": "com.test.channel",
                "journey": "AUTH",
                "auto_link": True,
            },
        ),
        call(
            "loyalty_card_add_auth",
            {
                "loyalty_plan_id": loyalty_plan_id,
                "loyalty_card_id": loyalty_card_id,
                "entry_id": entry_id,
                "user_id": user_id,
                "channel_slug": "com.test.channel",
                "journey": "AUTH",
                "auto_link": True,
                "consents": [],
                "authorise_fields": [
                    {"credential_slug": "email", "value": email},
                    {"credential_slug": "password", "value": password},
                ],
                "add_fields": [{"credential_slug": "card_number", "value": card_number}],
            },
        ),
    ]


@pytest.mark.parametrize(
    "link_status",
    [LoyaltyCardStatus.INVALID_CREDENTIALS, LoyaltyCardStatus.ACTIVE],
    ids=("link_status_INVALID_CREDENTIALS", "link_status_ACTIVE"),
)
@patch.object(LoyaltyCardHandler, "_dispatch_outcome_event")
@patch.object(LoyaltyCardHandler, "_dispatch_request_event")
@patch("angelia.handlers.loyalty_card.LoyaltyCardHandler.check_auth_credentials_against_existing")
@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_authorise_card_with_existing_credentials_outcome_events_200(
    mock_send_message_to_hermes: "MagicMock",
    mock_check_auth: "MagicMock",
    mock_request_event: "MagicMock",
    mock_outcome_event: "MagicMock",
    db_session: "Session",
    link_status: LoyaltyCardStatus,
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
) -> None:
    """
    Tests authorising a card has the same credentials as existing credentials.
    Also test failed outcome event
    """
    mock_check_auth.return_value = (True, True)

    set_vault_cache(to_load=["aes-keys"])
    card_number = "9511143200133540455525"
    email = "my_email@email.com"
    password = "iLoveTests33"
    payload = {
        "account": {
            "add_fields": {
                "credentials": [
                    {"credential_slug": "card_number", "value": card_number},
                ]
            },
            "authorise_fields": {
                "credentials": [
                    {"credential_slug": "email", "value": "wrong@email.com"},
                    {"credential_slug": "password", "value": "DifferentPass1"},
                ]
            },
        }
    }

    loyalty_plan, _channel, user = setup_plan_channel_and_user(slug="test-scheme")
    user_id = user.id
    db_session.commit()
    questions = setup_questions(loyalty_plan)

    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)
    db_session.commit()
    loyalty_card_id = loyalty_card_to_update.id

    association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id, user_id=user.id, link_status=link_status
    )

    auth_questions = {q.type: q.id for q in questions if q.auth_field}
    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

    LoyaltyCardAnswerFactory(
        question_id=auth_questions["email"],
        scheme_account_entry_id=association.id,
        answer=email,
    )
    LoyaltyCardAnswerFactory(
        question_id=auth_questions["password"],
        scheme_account_entry_id=association.id,
        answer=cipher.encrypt(password).decode(),
    )

    db_session.commit()

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{loyalty_card_to_update.id}/authorise",
        json=payload,
        method="PUT",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == falcon.HTTP_200
    assert resp.json == {"id": loyalty_card_id}
    assert mock_request_event.called
    if link_status == LoyaltyCardStatus.ACTIVE:
        mock_outcome_event.assert_called_once_with(success=True)
    else:
        # Call failed outcome_event because card is not in authorised state
        mock_outcome_event.assert_called_once_with(success=False)
    mock_send_message_to_hermes.assert_not_called()


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_handle_authorise_card_unchanged_add_field_different_creds_202(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
) -> None:
    """
    Tests authorising a card that is not in WALLET_ONLY state where the given credentials do not match those existing.
    """
    set_vault_cache(to_load=["aes-keys"])

    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    db_session.flush()
    questions = setup_questions(loyalty_plan)

    existing_user = UserFactory(client=channel.client_application)
    db_session.commit()

    card_number = "9511143200133540455525"
    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)
    db_session.commit()
    loyalty_card_id = loyalty_card_to_update.id

    association1 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=existing_user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )
    db_session.flush()
    entry_id = association2.id

    auth_questions = {q.type: q.id for q in questions if q.auth_field}
    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

    LoyaltyCardAnswerFactory(
        question_id=auth_questions["email"],
        scheme_account_entry_id=association1.id,
        answer="orig_wrong_email@oops.com",
    )
    LoyaltyCardAnswerFactory(
        question_id=auth_questions["password"],
        scheme_account_entry_id=association1.id,
        answer=cipher.encrypt("some_bad_password").decode(),
    )

    LoyaltyCardAnswerFactory(
        question_id=auth_questions["email"],
        scheme_account_entry_id=association2.id,
        answer="orig_wrong_email@oops.com",
    )
    LoyaltyCardAnswerFactory(
        question_id=auth_questions["password"],
        scheme_account_entry_id=association2.id,
        answer=cipher.encrypt("some_bad_password").decode(),
    )

    db_session.commit()

    payload = {
        "account": {
            "add_fields": {
                "credentials": [
                    {"credential_slug": "card_number", "value": card_number},
                ]
            },
            "authorise_fields": {
                "credentials": [
                    {"credential_slug": "email", "value": "wrong@email.com"},
                    {"credential_slug": "password", "value": "DifferentPass1"},
                ]
            },
        }
    }
    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{loyalty_card_to_update.id}/authorise",
        json=payload,
        method="PUT",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == falcon.HTTP_202
    assert resp.json == {"id": loyalty_card_id}
    assert mock_send_message_to_hermes.mock_calls == [
        call(
            "add_auth_request_event",
            {
                "loyalty_plan_id": loyalty_plan_id,
                "loyalty_card_id": loyalty_card_id,
                "entry_id": entry_id,
                "user_id": user_id,
                "channel_slug": "com.test.channel",
                "journey": "AUTH",
                "auto_link": True,
            },
        ),
        call(
            "loyalty_card_add_auth",
            {
                "loyalty_plan_id": loyalty_plan_id,
                "loyalty_card_id": loyalty_card_id,
                "entry_id": entry_id,
                "user_id": user_id,
                "channel_slug": "com.test.channel",
                "journey": "AUTH",
                "auto_link": True,
                "consents": [],
                "authorise_fields": [
                    {"credential_slug": "email", "value": "wrong@email.com"},
                    {"credential_slug": "password", "value": "DifferentPass1"},
                ],
                "add_fields": [{"credential_slug": "card_number", "value": card_number}],
            },
        ),
    ]


@patch.object(LoyaltyCardHandler, "_dispatch_request_event")
@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_handle_authorise_card_updated_add_field_creates_new_acc(
    mock_send_message_to_hermes: "MagicMock",
    mock_request_event: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
) -> None:
    """
    Tests authorise where the add field provided is different to that of the account in the URI.
    This should create a new account.
    """
    set_vault_cache(to_load=["aes-keys"])
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    db_session.flush()

    setup_questions(loyalty_plan)

    card_number1 = "9511143200133540455525"
    card_number2 = "9511143200133540466666"
    payload = {
        "account": {
            "add_fields": {
                "credentials": [
                    {"credential_slug": "card_number", "value": card_number2},
                ]
            },
            "authorise_fields": {
                "credentials": [
                    {"credential_slug": "email", "value": "my_email@email.com"},
                    {"credential_slug": "password", "value": "iLoveTests33"},
                ]
            },
        }
    }

    db_session.commit()

    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number1)
    db_session.commit()
    loyalty_card_id = loyalty_card_to_update.id

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )
    db_session.commit()

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{loyalty_card_to_update.id}/authorise",
        json=payload,
        method="PUT",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == falcon.HTTP_202

    user_associations = (
        db_session.execute(select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user_id))
        .scalars()
        .all()
    )

    assert len(user_associations) == 2
    new_assoc = next(assoc for assoc in user_associations if assoc.scheme_account_id != loyalty_card_id)
    new_card_id = new_assoc.scheme_account_id
    assert mock_request_event.called
    assert mock_send_message_to_hermes.mock_calls == [
        call(
            "delete_loyalty_card",
            {
                "loyalty_plan_id": loyalty_plan_id,
                "loyalty_card_id": loyalty_card_id,
                "entry_id": new_assoc.id,  # should perhaps be the old assoc id but msg the recipient does not use it
                "user_id": user_id,
                "channel_slug": "com.test.channel",
                "journey": "DELETE",
                "auto_link": True,
            },
        ),
        call(
            "loyalty_card_add_auth",
            {
                "loyalty_plan_id": loyalty_plan_id,
                "loyalty_card_id": new_card_id,
                "entry_id": new_assoc.id,
                "user_id": user_id,
                "channel_slug": "com.test.channel",
                "journey": "ADD_AND_AUTH",
                "auto_link": True,
                "consents": [],
                "authorise_fields": [
                    {"credential_slug": "email", "value": "my_email@email.com"},
                    {"credential_slug": "password", "value": "iLoveTests33"},
                ],
                "add_fields": [{"credential_slug": "card_number", "value": "9511143200133540466666"}],
            },
        ),
    ]

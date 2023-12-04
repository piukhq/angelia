import typing
from unittest.mock import patch

import arrow
import falcon
import pytest
from sqlalchemy import func, select

from app.handlers.loyalty_card import TRUSTED_ADD, LoyaltyCardHandler
from app.hermes.models import (
    Channel,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    User,
)
from app.lib.loyalty_card import LoyaltyCardStatus, OriginatingJourney
from tests.factories import (
    LoyaltyCardAnswerFactory,
    LoyaltyCardFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanQuestionFactory,
    UserFactory,
)
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session


@pytest.fixture
def trusted_add_answer_fields(trusted_add_req_data: dict) -> None:
    """The account_id field in the request data is converted by the serializer into merchant_identifier.
    Since the data isn't serialized for these tests we need to do the conversion for the handler to process
    correctly.
    """
    answer_fields = trusted_add_req_data["account"]
    answer_fields["merchant_fields"] = {"merchant_identifier": answer_fields["merchant_fields"]["account_id"]}

    return answer_fields


@pytest.fixture(scope="function")
def mock_middleware_hermes_message() -> "typing.Generator[MagicMock, None, None]":
    with patch("app.api.middleware.send_message_to_hermes") as mocked_send_to_hermes:
        yield mocked_send_to_hermes


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_201(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mock_middleware_hermes_message: "MagicMock",
) -> None:
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    setup_questions(loyalty_plan)
    db_session.flush()

    card_number = "9511143200133540455525"
    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "add_fields": {
                "credentials": [
                    {
                        "credential_slug": "card_number",
                        "value": card_number,
                    }
                ]
            },
            "merchant_fields": {
                "account_id": "Z99783494A",
            },
        },
    }
    assert db_session.scalar(select(func.count(SchemeAccount.id))) == 0
    assert (
        db_session.scalar(
            select(func.count(SchemeAccountUserAssociation.id)).where(SchemeAccountUserAssociation.user_id == user.id)
        )
        == 0
    )

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        method="POST",
        json=payload,
        user_id=user_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_201
    assert db_session.scalar(select(func.count(SchemeAccount.id))) == 1
    entry = db_session.execute(
        select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user_id)
    ).scalar_one_or_none()

    assert entry
    loyalty_card = entry.scheme_account
    expected_account_id = payload["account"]["merchant_fields"]["account_id"].lower()  # <-- lower case correct? FIXME?
    assert loyalty_card.merchant_identifier == expected_account_id
    assert entry.link_status == LoyaltyCardStatus.ACTIVE
    assert loyalty_card.originating_journey == OriginatingJourney.ADD
    assert loyalty_card.link_date
    assert mock_send_message_to_hermes.call_args_list[0][0] == (
        "loyalty_card_trusted_add",
        {
            "user_id": user_id,
            "add_fields": [
                {
                    "credential_slug": "card_number",
                    "value": card_number,
                }
            ],
            "authorise_fields": [],
            "auto_link": True,
            "channel_slug": "com.test.channel",
            "consents": None,
            "entry_id": entry.id,
            "journey": "TRUSTED_ADD",
            "loyalty_card_id": loyalty_card.id,
            "loyalty_plan_id": loyalty_plan_id,
            "merchant_fields": [
                {
                    "credential_slug": "merchant_identifier",
                    "value": expected_account_id,
                }
            ],
        },
    )
    mock_middleware_hermes_message.assert_not_called()
    assert mock_send_message_to_hermes.call_args_list[1][0] == (
        "loyalty_card_trusted_add_success_event",
        {
            "user_id": user_id,
            "channel_slug": "com.test.channel",
            "loyalty_card_id": loyalty_card.id,
            "entry_id": entry.id,
        },
    )


def test_on_post_trusted_add_incorrect_payload_422(mock_middleware_hermes_message: "MagicMock") -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        json={"dead": "beef"},
        method="POST",
        user_id=1,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_422
    assert resp.json["error_message"] == "Could not validate fields"
    assert resp.json["error_slug"] == "FIELD_VALIDATION_ERROR"
    assert "extra keys not allowed @ data['dead']" in resp.json["fields"]
    assert "required key not provided @ data['account']" in resp.json["fields"]
    assert "required key not provided @ data['loyalty_plan_id']" in resp.json["fields"]
    mock_middleware_hermes_message.assert_not_called()


def test_on_post_trusted_add_malformed_payload_400(mock_middleware_hermes_message: "MagicMock") -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
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
    mock_middleware_hermes_message.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_201_existing_matching_credentials(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mock_middleware_hermes_message: "MagicMock",
) -> None:
    loyalty_plan, channel, user1 = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user1_id = loyalty_plan.id, user1.id
    questions = setup_questions(loyalty_plan)
    db_session.flush()

    card_number = "9511143200133540455525"
    merchant_identifier = "12e34r3edvcsd"

    user2 = UserFactory(client=channel.client_application)
    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number=card_number, merchant_identifier=merchant_identifier
    )

    db_session.flush()

    user2_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=question_id,
        scheme_account_entry_id=user2_association.id,
        answer=merchant_identifier,
    )
    db_session.commit()

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user1.id)
    assert not db_session.execute(user_link_q).scalar_one_or_none()

    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "add_fields": {
                "credentials": [
                    {
                        "credential_slug": "card_number",
                        "value": card_number,
                    }
                ]
            },
            "merchant_fields": {
                "account_id": merchant_identifier,
            },
        },
    }
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        method="POST",
        json=payload,
        user_id=user1_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_201

    link = db_session.execute(user_link_q).scalar_one_or_none()
    assert link
    assert link.link_status == LoyaltyCardStatus.ACTIVE
    assert mock_send_message_to_hermes.call_args_list[0][0] == (
        "loyalty_card_trusted_add",
        {
            "user_id": user1_id,
            "add_fields": [
                {
                    "credential_slug": "card_number",
                    "value": card_number,
                }
            ],
            "authorise_fields": [],
            "auto_link": True,
            "channel_slug": "com.test.channel",
            "consents": None,
            "entry_id": link.id,
            "journey": "TRUSTED_ADD",
            "loyalty_card_id": existing_card.id,
            "loyalty_plan_id": loyalty_plan_id,
            "merchant_fields": [
                {
                    "credential_slug": "merchant_identifier",
                    "value": merchant_identifier,
                }
            ],
        },
    )
    mock_middleware_hermes_message.assert_not_called()
    assert mock_send_message_to_hermes.call_args_list[1][0] == (
        "loyalty_card_trusted_add_success_event",
        {
            "user_id": user1_id,
            "channel_slug": "com.test.channel",
            "loyalty_card_id": existing_card.id,
            "entry_id": link.id,
        },
    )


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_200_same_wallet_existing_matching_credentials_sets_active(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mock_middleware_hermes_message: "MagicMock",
) -> None:
    """
    Tests scenario where a user adds a card via non-trusted means and then via trusted_add.
    This should set the card to active and save the merchant identifier if the account was in pending state
    """
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    setup_questions(loyalty_plan)
    db_session.flush()
    card_number = "9511143200133540455525"
    merchant_identifier = "12e34r3edvcsd"

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number=card_number, merchant_identifier=merchant_identifier
    )
    db_session.flush()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.PENDING,
    )

    db_session.commit()

    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "add_fields": {
                "credentials": [
                    {
                        "credential_slug": "card_number",
                        "value": card_number,
                    }
                ]
            },
            "merchant_fields": {
                "account_id": merchant_identifier,
            },
        },
    }
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        method="POST",
        json=payload,
        user_id=user_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_200

    link = db_session.execute(
        select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user_id)
    ).scalar_one_or_none()
    assert link
    assert link.link_status == LoyaltyCardStatus.ACTIVE
    assert mock_send_message_to_hermes.call_args_list[0][0] == (
        "loyalty_card_trusted_add",
        {
            "user_id": user_id,
            "add_fields": [
                {
                    "credential_slug": "card_number",
                    "value": card_number,
                }
            ],
            "authorise_fields": [],
            "auto_link": True,
            "channel_slug": "com.test.channel",
            "consents": None,
            "entry_id": link.id,
            "journey": "TRUSTED_ADD",
            "loyalty_card_id": link.scheme_account_id,
            "loyalty_plan_id": loyalty_plan_id,
            "merchant_fields": [
                {
                    "credential_slug": "merchant_identifier",
                    "value": merchant_identifier,
                }
            ],
        },
    )
    mock_middleware_hermes_message.assert_not_called()
    assert mock_send_message_to_hermes.call_count == 1


TEST_DATE = arrow.get("2022-12-12").isoformat()


@pytest.mark.parametrize(
    "link_date,join_date", [(None, None), (TEST_DATE, None), (None, TEST_DATE), (TEST_DATE, TEST_DATE)]
)
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_same_wallet_existing_matching_credentials_sets_link_date(
    mock_send_message_to_hermes: "MagicMock",
    link_date: str | None,
    join_date: str | None,
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mock_middleware_hermes_message: "MagicMock",
) -> None:
    """
    Tests that link_date is set when a user has an unauthorised card via non-trusted means and then the card is
    added via trusted_add.
    """
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    setup_questions(loyalty_plan)
    db_session.flush()
    card_number = "9511143200133540455525"
    merchant_identifier = "12e34r3edvcsd"

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=card_number,
        merchant_identifier=merchant_identifier,
        link_date=link_date,
        join_date=join_date,
    )
    db_session.flush()
    existing_card_id = existing_card.id

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.PENDING,
    )

    db_session.commit()

    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "add_fields": {
                "credentials": [
                    {
                        "credential_slug": "card_number",
                        "value": card_number,
                    }
                ]
            },
            "merchant_fields": {
                "account_id": merchant_identifier,
            },
        },
    }
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        method="POST",
        json=payload,
        user_id=user_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_200
    assert mock_send_message_to_hermes.called

    existing_card = db_session.scalar(select(SchemeAccount).where(SchemeAccount.id == existing_card_id))
    if not (link_date or join_date):
        assert existing_card.link_date
    elif join_date and not link_date:
        assert existing_card.join_date == arrow.get(TEST_DATE).datetime
        assert not existing_card.link_date
    elif link_date and not join_date:
        assert existing_card.link_date == arrow.get(TEST_DATE).datetime
        assert not existing_card.join_date
    else:
        # not likely to happen where both join_date and link_date are populated
        # but nothing should be updated in this scenario
        assert existing_card.join_date == arrow.get(TEST_DATE).datetime
        assert existing_card.link_date == arrow.get(TEST_DATE).datetime

    mock_middleware_hermes_message.assert_not_called()


@pytest.mark.parametrize("credential", ["account_id", "card_number"])
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_409_existing_non_matching_credentials(
    mock_send_message_to_hermes: "MagicMock",
    credential: str,
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mock_middleware_hermes_message: "MagicMock",
) -> None:
    loyalty_plan, channel, user1 = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user1_id = loyalty_plan.id, user1.id
    questions = setup_questions(loyalty_plan)
    db_session.flush()

    card_number = "999999999934092840233"
    account_id = "sdf223jlk342"

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=card_number,
        merchant_identifier=account_id,
    )
    user2 = UserFactory(client=channel.client_application)
    db_session.flush()

    user2_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=question_id,
        scheme_account_entry_id=user2_association.id,
        answer=account_id,
    )
    db_session.commit()

    match credential:
        case "card_number":
            scheme_account_id = existing_card.id
            credential_value = existing_card.card_number
            merchant_account_id = "11111111"
        case "account_id":
            scheme_account_id = None
            credential_value = "11111111"
            merchant_account_id = account_id
        case _:
            ValueError(f"credential {credential} not supported.")

    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "add_fields": {
                "credentials": [
                    {
                        "credential_slug": "card_number",
                        "value": credential_value,
                    }
                ]
            },
            "merchant_fields": {
                "account_id": merchant_account_id,
            },
        },
    }

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        method="POST",
        json=payload,
        user_id=user1_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )

    assert resp.status == falcon.HTTP_409
    err_resp = {
        "account_id": "A loyalty card with this account_id has already been added in a wallet, "
        "but the key credential does not match.",
        "card_number": "A loyalty card with this key credential has already been added "
        "in a wallet, but the account_id does not match.",
    }
    assert resp.json == {
        "error_message": err_resp[credential],
        "error_slug": "CONFLICT",
    }
    assert (
        db_session.scalar(
            select(func.count(SchemeAccountUserAssociation.id)).where(SchemeAccountUserAssociation.user_id == user1_id)
        )
        == 0
    )

    mock_send_message_to_hermes.assert_not_called()
    mock_middleware_hermes_message.assert_called_once_with(
        "add_trusted_failed",
        {
            "loyalty_plan_id": loyalty_plan_id,
            "loyalty_card_id": scheme_account_id,
            "user_id": user1_id,
            "channel_slug": "com.test.channel",
        },
    )


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_multi_wallet_existing_key_cred_matching_credentials(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    mock_middleware_hermes_message: "MagicMock",
) -> None:
    """
    This test replicates Squaremeal-type schemes which use an auth field to add a card and also have
    the merchant return a card number. This leads to having both card_number and alt_main_answer
    populated on the scheme account. The test ensures that validation is done against the correct field
    when checking the unique-together-ness of the key credential(email) and merchant_identifier.
    """
    loyalty_plan, channel, user1 = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user1_id = loyalty_plan.id, user1.id
    db_session.flush()

    merchant_identifier = "sdf223jlk342"

    questions = [
        LoyaltyPlanQuestionFactory(
            id=1,
            scheme_id=loyalty_plan.id,
            type="card_number",
            label="Card Number",
            add_field=False,
            manual_question=False,
        ),
        LoyaltyPlanQuestionFactory(
            id=3,
            scheme_id=loyalty_plan.id,
            type="email",
            label="Email",
            auth_field=True,
            manual_question=True,
        ),
        LoyaltyPlanQuestionFactory(
            id=4,
            scheme_id=loyalty_plan.id,
            type="password",
            label="Password",
            auth_field=True,
        ),
        LoyaltyPlanQuestionFactory(
            id=7,
            scheme_id=loyalty_plan.id,
            type="merchant_identifier",
            label="Merchant Identifier",
            third_party_identifier=True,
            options=7,
        ),
    ]

    user2 = UserFactory(client=channel.client_application)
    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="111111111111",
        merchant_identifier=merchant_identifier,
        alt_main_answer="someemail@bink.com",
    )
    db_session.flush()

    user2_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=question_id,
        scheme_account_entry_id=user2_association.id,
        answer=merchant_identifier,
    )
    db_session.commit()

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user1.id)
    user_links_before = db_session.execute(user_link_q).all()

    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "authorise_fields": {
                "credentials": [
                    {
                        "credential_slug": "email",
                        "value": "someemail@bink.com",
                    }
                ]
            },
            "merchant_fields": {
                "account_id": merchant_identifier,
            },
        },
    }

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        method="POST",
        json=payload,
        user_id=user1_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )

    assert resp.status == falcon.HTTP_201

    assert len(user_links_before) == 0
    link = db_session.execute(user_link_q).scalar_one_or_none()
    assert link
    assert link.link_status == LoyaltyCardStatus.ACTIVE
    assert mock_send_message_to_hermes.call_args_list[0][0] == (
        "loyalty_card_trusted_add",
        {
            "user_id": user1_id,
            "add_fields": [
                {
                    "credential_slug": "email",
                    "value": "someemail@bink.com",
                }
            ],
            "authorise_fields": [],
            "auto_link": True,
            "channel_slug": "com.test.channel",
            "consents": None,
            "entry_id": link.id,
            "journey": "TRUSTED_ADD",
            "loyalty_card_id": link.scheme_account_id,
            "loyalty_plan_id": loyalty_plan_id,
            "merchant_fields": [
                {
                    "credential_slug": "merchant_identifier",
                    "value": merchant_identifier,
                }
            ],
        },
    )
    mock_middleware_hermes_message.assert_not_called()

    assert mock_send_message_to_hermes.call_args_list[1][0] == (
        "loyalty_card_trusted_add_success_event",
        {
            "user_id": user1_id,
            "channel_slug": "com.test.channel",
            "loyalty_card_id": link.scheme_account_id,
            "entry_id": link.id,
        },
    )


@pytest.mark.parametrize("credential", ["merchant_identifier", "email"])
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_multi_wallet_existing_key_cred_non_matching_credentials(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    credential: str,
    mock_middleware_hermes_message: "MagicMock",
) -> None:
    """
    This test replicates Squaremeal-type schemes which use an auth field to add a card and also have
    the merchant return a card number. This leads to having both card_number and alt_main_answer
    populated on the scheme account. The test ensures that validation is done against the correct field
    when checking the unique-together-ness of the key credential(email) and merchant_identifier.
    """
    loyalty_plan, channel, user1 = setup_plan_channel_and_user(slug="test-scheme")
    loyalty_plan_id, user1_id = loyalty_plan.id, user1.id
    db_session.flush()
    credentials = {"email": "someemail@bink.com", "merchant_identifier": "12e34r3edvcsd"}
    credentials.update({credential: "111111111111"})

    questions = [
        LoyaltyPlanQuestionFactory(
            id=1,
            scheme_id=loyalty_plan.id,
            type="card_number",
            label="Card Number",
            add_field=False,
            manual_question=False,
        ),
        LoyaltyPlanQuestionFactory(
            id=3,
            scheme_id=loyalty_plan.id,
            type="email",
            label="Email",
            auth_field=True,
            manual_question=True,
        ),
        LoyaltyPlanQuestionFactory(id=4, scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True),
        LoyaltyPlanQuestionFactory(
            id=7,
            scheme_id=loyalty_plan.id,
            type="merchant_identifier",
            label="Merchant Identifier",
            third_party_identifier=True,
            options=7,
        ),
    ]

    user2 = UserFactory(client=channel.client_application)
    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="111111111111",
        merchant_identifier=credentials["merchant_identifier"],
        alt_main_answer=credentials["email"],
    )
    db_session.flush()
    event_card_id = existing_card.id if credential == "merchant_identifier" else None

    association1 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=question_id,
        scheme_account_entry_id=association1.id,
        answer=credentials["merchant_identifier"],
    )
    db_session.commit()

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user1.id)
    assert len(db_session.execute(user_link_q).all()) == 0

    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "authorise_fields": {
                "credentials": [
                    {
                        "credential_slug": "email",
                        "value": "someemail@bink.com",
                    }
                ]
            },
            "merchant_fields": {
                "account_id": "12e34r3edvcsd",
            },
        },
    }

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        method="POST",
        json=payload,
        user_id=user1_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409

    err_resp = {
        "email": "A loyalty card with this account_id has already been added in a wallet, "
        "but the key credential does not match.",
        "merchant_identifier": "A loyalty card with this key credential has already been added "
        "in a wallet, but the account_id does not match.",
    }
    assert resp.json == {
        "error_message": err_resp[credential],
        "error_slug": "CONFLICT",
    }

    link = db_session.execute(user_link_q).scalar_one_or_none()
    assert not link
    mock_send_message_to_hermes.assert_not_called()
    mock_middleware_hermes_message.assert_called_once_with(
        "add_trusted_failed",
        {
            "channel_slug": "com.test.channel",
            "loyalty_card_id": event_card_id,
            "loyalty_plan_id": loyalty_plan_id,
            "user_id": user1_id,
        },
    )


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_add_201(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    loyalty_plan_id, user_id = loyalty_plan.id, user.id
    db_session.flush()
    card_number = "9511143200133540455525"
    old_merchant_identifier = "sdf223jlk342"
    new_merchant_identifier = "sdf223lh456j"

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number=card_number, merchant_identifier=old_merchant_identifier
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user_id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=card_number,
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=old_merchant_identifier,
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {"credentials": [{"credential_slug": "card_number", "value": card_number}]},
            "merchant_fields": {"account_id": new_merchant_identifier},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_201
    entries = (
        db_session.execute(select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user_id))
        .scalars()
        .all()
    )
    for entry in entries:
        association = entry if entry.scheme_account.merchant_identifier == new_merchant_identifier else None
    assert association
    loyalty_card = association.scheme_account
    assert resp.json == {
        "id": loyalty_card.id,
    }
    expected_account_id = new_merchant_identifier
    assert loyalty_card.merchant_identifier == expected_account_id
    assert association.link_status == LoyaltyCardStatus.ACTIVE
    assert loyalty_card.originating_journey == OriginatingJourney.ADD
    assert loyalty_card.link_date
    assert mock_send_message_to_hermes.call_count == 3
    mock_hermes_call_routes = [args.args[0] for args in mock_send_message_to_hermes.call_args_list]
    assert "delete_loyalty_card" in mock_hermes_call_routes
    assert "add_auth_request_event" in mock_hermes_call_routes
    assert "loyalty_card_trusted_add" in mock_hermes_call_routes
    mock_send_message_to_hermes.assert_called_with(
        "loyalty_card_trusted_add",
        {
            "loyalty_plan_id": loyalty_plan_id,
            "loyalty_card_id": loyalty_card.id,
            "entry_id": association.id,
            "user_id": user_id,
            "channel_slug": "com.test.channel",
            "journey": "TRUSTED_ADD",
            "auto_link": True,
            "consents": [],
            "authorise_fields": [],
            "merchant_fields": [{"credential_slug": "merchant_identifier", "value": new_merchant_identifier}],
            "add_fields": [{"credential_slug": "card_number", "value": card_number}],
        },
    )


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_update_to_existing_merchant_identifier_and_existing_key_cred_success(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "jhv223lew342", "card_number": "11111111"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials_to_update["merchant_identifier"]}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    loyalty_plan_id, user_id = loyalty_plan.id, user.id

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    existing_card2 = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials_to_update["card_number"],
        merchant_identifier=credentials_to_update["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user_id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card2.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}]
            },
            "merchant_fields": {"account_id": credentials_to_update["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_201
    entries = (
        db_session.execute(select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user_id))
        .scalars()
        .all()
    )
    for entry in entries:
        association = (
            entry if entry.scheme_account.merchant_identifier == credentials_to_update["merchant_identifier"] else None
        )
    assert association
    loyalty_card = association.scheme_account
    assert resp.json == {
        "id": loyalty_card.id,
    }
    expected_account_id = credentials_to_update["merchant_identifier"]
    assert loyalty_card.merchant_identifier == expected_account_id
    assert association.link_status == LoyaltyCardStatus.ACTIVE
    assert loyalty_card.link_date
    assert mock_send_message_to_hermes.call_count == 3
    mock_hermes_call_routes = [args.args[0] for args in mock_send_message_to_hermes.call_args_list]
    assert "delete_loyalty_card" in mock_hermes_call_routes
    assert "add_auth_request_event" in mock_hermes_call_routes
    assert "loyalty_card_trusted_add" in mock_hermes_call_routes
    mock_send_message_to_hermes.assert_called_with(
        "loyalty_card_trusted_add",
        {
            "loyalty_plan_id": loyalty_plan_id,
            "loyalty_card_id": loyalty_card.id,
            "entry_id": association.id,
            "user_id": user_id,
            "channel_slug": "com.test.channel",
            "journey": "TRUSTED_ADD",
            "auto_link": True,
            "consents": [],
            "authorise_fields": [],
            "merchant_fields": [
                {"credential_slug": "merchant_identifier", "value": credentials_to_update["merchant_identifier"]}
            ],
            "add_fields": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}],
        },
    )


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_add_409_existing_key_credential(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"card_number": "11111111"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials["merchant_identifier"]}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    existing_card2 = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials_to_update["card_number"],
        merchant_identifier="00000000000000",
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card2.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer="00000000000000",
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}]
            },
            "merchant_fields": {"account_id": credentials["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "A loyalty card with this key credential has already been added in a wallet, "
        "but the account_id does not match.",
        "error_slug": "CONFLICT",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_add_409_existing_merchant_identifier(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "jhv223lew342"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials_to_update["merchant_identifier"]}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    existing_card2 = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="00000000000000",
        merchant_identifier=credentials_to_update["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card2.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer="00000000000000",
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {"credentials": [{"credential_slug": "card_number", "value": credentials["card_number"]}]},
            "merchant_fields": {"account_id": credentials_to_update["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "A loyalty card with this account_id has already been added in a wallet, "
        "but the key credential does not match.",
        "error_slug": "CONFLICT",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_add_409_update_key_cred_and_existing_merchant_identifier(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "1234567890", "card_number": "11111111"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials_to_update["merchant_identifier"]}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    existing_card2 = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="00000000000000",
        merchant_identifier=credentials_to_update["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card2.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer="00000000000000",
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {"credentials": [{"credential_slug": "card_number", "value": credentials["card_number"]}]},
            "merchant_fields": {"account_id": credentials_to_update["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "A loyalty card with this account_id has already been added in a wallet, "
        "but the key credential does not match.",
        "error_slug": "CONFLICT",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_add_409_update_merchant_identifier_and_existing_key_cred(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "1234567890", "card_number": "11111111"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials_to_update["merchant_identifier"]}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    existing_card2 = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials_to_update["card_number"],
        merchant_identifier="00000000000000",
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card2.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer="00000000000000",
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}]
            },
            "merchant_fields": {"account_id": credentials["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "A loyalty card with this key credential has already been added in a wallet, "
        "but the account_id does not match.",
        "error_slug": "CONFLICT",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_201_update_shared_card_update_success(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    """
    Tests a successful update when a two users share a card and one attempts an update via PUT add_trusted.
    Both the merchant_identifier and key credential must be updated to prevent creation of an account with
    a duplicate value for the key credential/merchant identifier.
    """
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "jhv223lew342", "card_number": "11111111"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials_to_update["merchant_identifier"]}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    loyalty_plan_id, user_id = loyalty_plan.id, user.id

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user_id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}]
            },
            "merchant_fields": {"account_id": credentials_to_update["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user_id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_201
    entries = (
        db_session.execute(select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user_id))
        .scalars()
        .all()
    )
    for entry in entries:
        association = (
            entry if entry.scheme_account.merchant_identifier == credentials_to_update["merchant_identifier"] else None
        )
    assert association
    loyalty_card = association.scheme_account
    assert resp.json == {
        "id": loyalty_card.id,
    }
    expected_account_id = credentials_to_update["merchant_identifier"]
    assert loyalty_card.merchant_identifier == expected_account_id
    assert association.link_status == LoyaltyCardStatus.ACTIVE
    assert loyalty_card.link_date
    assert mock_send_message_to_hermes.call_count == 3
    mock_hermes_call_routes = [args.args[0] for args in mock_send_message_to_hermes.call_args_list]
    assert "delete_loyalty_card" in mock_hermes_call_routes
    assert "add_auth_request_event" in mock_hermes_call_routes
    assert "loyalty_card_trusted_add" in mock_hermes_call_routes
    mock_send_message_to_hermes.assert_called_with(
        "loyalty_card_trusted_add",
        {
            "loyalty_plan_id": loyalty_plan_id,
            "loyalty_card_id": loyalty_card.id,
            "entry_id": association.id,
            "user_id": user_id,
            "channel_slug": "com.test.channel",
            "journey": "TRUSTED_ADD",
            "auto_link": True,
            "consents": [],
            "authorise_fields": [],
            "merchant_fields": [
                {"credential_slug": "merchant_identifier", "value": credentials_to_update["merchant_identifier"]}
            ],
            "add_fields": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}],
        },
    )


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_update_shared_card_update_only_key_cred_fails(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"card_number": "11111111"}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}]
            },
            "merchant_fields": {"account_id": credentials["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "A loyalty card with this account_id has already been added in a wallet, "
        "but the key credential does not match.",
        "error_slug": "CONFLICT",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_update_shared_card_update_only_merchant_identifier_fails(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "11111111"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials_to_update["merchant_identifier"]}
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {"credentials": [{"credential_slug": "card_number", "value": credentials["card_number"]}]},
            "merchant_fields": {"account_id": credentials_to_update["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "A loyalty card with this key credential has already been added in a wallet, "
        "but the account_id does not match.",
        "error_slug": "CONFLICT",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_update_to_card_already_in_wallet_key_cred_and_merchant_identifier(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "1234567890", "card_number": "11111111"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials_to_update["merchant_identifier"]}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    db_session.flush()
    user_id = user.id

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    existing_card2 = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials_to_update["card_number"],
        merchant_identifier=credentials_to_update["merchant_identifier"],
    )
    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card2.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}]
            },
            "merchant_fields": {"account_id": credentials_to_update["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_200
    entries = (
        db_session.execute(select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user_id))
        .scalars()
        .all()
    )
    for entry in entries:
        association = (
            entry if entry.scheme_account.merchant_identifier == credentials_to_update["merchant_identifier"] else None
        )
    assert association
    loyalty_card = association.scheme_account
    assert resp.json == {
        "id": loyalty_card.id,
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_update_to_card_already_in_wallet_single_credential(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "1234567890", "card_number": "11111111"}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    existing_card2 = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials_to_update["card_number"],
        merchant_identifier=credentials_to_update["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card2.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "card_number", "value": credentials_to_update["card_number"]}]
            },
            "merchant_fields": {"account_id": credentials["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "A loyalty card with this key credential has already been added in a wallet, "
        "but the account_id does not match.",
        "error_slug": "CONFLICT",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_update_to_card_already_in_wallet_merchant_identifier(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    credentials_to_update = {"merchant_identifier": "1234567890", "card_number": "11111111"}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials_to_update["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    user2 = UserFactory(client=user.client)
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    existing_card2 = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials_to_update["card_number"],
        merchant_identifier=credentials_to_update["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    user_association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card2.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association2.id,
        answer=credentials_to_update["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {"credentials": [{"credential_slug": "card_number", "value": credentials["card_number"]}]},
            "merchant_fields": {"account_id": credentials_to_update["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "A loyalty card with this account_id has already been added in a wallet, "
        "but the key credential does not match.",
        "error_slug": "CONFLICT",
    }
    mock_send_message_to_hermes.assert_not_called()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_trusted_update_to_card_already_in_wallet_same_credentials(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    credentials = {"merchant_identifier": "sdf223jlk342", "card_number": "9511143200133540455525"}
    trusted_add_answer_fields["merchant_fields"] = {"merchant_identifier": credentials["merchant_identifier"]}
    trusted_add_answer_fields["add_fields"]["credentials"] = [
        {"credential_slug": "card_number", "value": credentials["card_number"]}
    ]
    _, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )
    db_session.flush()

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )

    db_session.flush()

    user_association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    add_question_id = next(q.id for q in questions if q.add_field)
    merchant_identifier_question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=add_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["card_number"],
    )
    LoyaltyCardAnswerFactory(
        question_id=merchant_identifier_question_id,
        scheme_account_entry_id=user_association.id,
        answer=credentials["merchant_identifier"],
    )
    db_session.commit()

    payload = {
        "account": {
            "add_fields": {"credentials": [{"credential_slug": "card_number", "value": credentials["card_number"]}]},
            "merchant_fields": {"account_id": credentials["merchant_identifier"]},
        }
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{existing_card.id}/add_trusted",
        method="PUT",
        json=payload,
        user_id=user.id,
        channel="com.test.channel",
        is_trusted_channel=True,
    )

    assert resp.status == falcon.HTTP_200
    mock_send_message_to_hermes.assert_not_called()

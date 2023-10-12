import typing
from unittest.mock import patch

import arrow
import falcon
import pytest
from sqlalchemy import func, select

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


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_201(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
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

    mock_send_message_to_hermes.assert_called_once_with(
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


def test_on_post_trusted_add_incorrect_payload_422() -> None:
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


def test_on_post_trusted_add_malformed_payload_400() -> None:
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


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_201_existing_matching_credentials(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
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
    mock_send_message_to_hermes.assert_called_once_with(
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


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_200_same_wallet_existing_matching_credentials_sets_active(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
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

    mock_send_message_to_hermes.assert_called_once_with(
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


@pytest.mark.parametrize("credential", ["account_id", "card_number"])
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_trusted_add_409_existing_non_matching_credentials(
    mock_send_message_to_hermes: "MagicMock",
    credential: str,
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
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

    payload = {
        "loyalty_plan_id": loyalty_plan_id,
        "account": {
            "add_fields": {
                "credentials": [
                    {
                        "credential_slug": "card_number",
                        "value": existing_card.card_number if credential == "card_number" else "11111111",
                    }
                ]
            },
            "merchant_fields": {
                "account_id": account_id if credential == "account_id" else "11111111",
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


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_multi_wallet_existing_key_cred_matching_credentials(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
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
    mock_send_message_to_hermes.assert_called_once_with(
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


@pytest.mark.parametrize("credential", ["merchant_identifier", "email"])
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_multi_wallet_existing_key_cred_non_matching_credentials(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    credential: str,
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

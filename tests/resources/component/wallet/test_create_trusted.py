import typing
from unittest.mock import patch

import falcon
import pytest
from sqlalchemy import func, select

from app.hermes.models import (
    Channel,
    PaymentAccount,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    User,
)
from tests.factories import PaymentAccountUserAssociation, PaymentCardFactory
from tests.helpers.authenticated_request import get_authenticated_request
from tests.resources.component.config import MockAuthConfig

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
@patch("app.handlers.payment_account.send_message_to_hermes")
@patch("app.handlers.token.send_message_to_hermes")
@patch("app.resources.wallet.get_current_token_secret")
def test_on_post_create_trusted_201(
    current_token: "MagicMock",
    mock_send_message_to_hermes_token: "MagicMock",
    mock_send_message_to_hermes_payment: "MagicMock",
    mock_send_message_to_hermes_loyalty: "MagicMock",
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mock_middleware_hermes_message: "MagicMock",
) -> None:
    loyalty_plan, channel, _ = setup_plan_channel_and_user(slug="test-scheme", is_trusted_channel=True)
    channel.email_required = False
    db_session.flush()
    loyalty_plan_id = loyalty_plan.id
    setup_questions(loyalty_plan)
    db_session.flush()
    visa = PaymentCardFactory(slug="visa")
    db_session.add(visa)
    db_session.commit()

    mock_auth_config = MockAuthConfig(channel=channel)
    current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key
    visa_card_number = "4234563200133540455525"
    payload = {
        "token": {
            "grant_type": "b2b",
            "scope": ["user"],
        },
        "loyalty_card": {
            "loyalty_plan_id": loyalty_plan_id,
            "account": {
                "add_fields": {
                    "credentials": [
                        {
                            "credential_slug": "card_number",
                            "value": visa_card_number,
                        }
                    ]
                },
                "merchant_fields": {
                    "account_id": "Z99783494A",
                },
            },
        },
        "payment_card": {
            "issuer": "issuer",
            "name_on_card": "First Last",
            "card_nickname": "test-create-trusted",
            "expiry_month": "10",
            "expiry_year": "29",
            "token": "H7FdKWKPOPhepzxS4MfUuvTDHx7",
            "last_four_digits": "5525",
            "first_six_digits": "423456",
            "fingerprint": "b5fe350d5135ab64a8f3c1097fadefd9effb",
            "country": "GB",
            "currency_code": "GBP",
        },
    }
    assert db_session.scalar(select(func.count(SchemeAccount.id))) == 0

    resp = get_authenticated_request(
        path="/v2/wallet/create_trusted",
        method="POST",
        json=payload,
        channel=channel.bundle_id,
        is_trusted_channel=True,
    )
    assert resp.status == falcon.HTTP_201
    payment_account_id = db_session.execute(
        select(PaymentAccount.id).where(PaymentAccount.card_nickname == "test-create-trusted")
    ).scalar_one_or_none()
    user_id = db_session.execute(
        select(PaymentAccountUserAssociation.user_id).where(
            PaymentAccountUserAssociation.payment_card_account_id == payment_account_id
        )
    ).scalar_one_or_none()
    entry = db_session.execute(
        select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user_id)
    ).scalar_one_or_none()
    assert entry
    loyalty_card = entry.scheme_account
    assert resp.json == {
        "token": {
            "access_token": resp.json["token"]["access_token"],
            "token_type": "bearer",
            "expires_in": 54000,
            "refresh_token": resp.json["token"]["refresh_token"],
            "scope": ["user"],
        },
        "loyalty_card": {"id": loyalty_card.id},
        "payment_card": {"id": payment_account_id},
    }
    assert db_session.scalar(select(func.count(SchemeAccount.id))) == 1
    expected_account_id = payload["loyalty_card"]["account"]["merchant_fields"]["account_id"].lower()
    assert mock_send_message_to_hermes_loyalty.call_args_list[0][0] == (
        "loyalty_card_trusted_add",
        {
            "user_id": user_id,
            "add_fields": [
                {
                    "credential_slug": "card_number",
                    "value": visa_card_number,
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
    assert mock_send_message_to_hermes_loyalty.call_args_list[1][0] == (
        "loyalty_card_trusted_add_success_event",
        {
            "user_id": user_id,
            "channel_slug": "com.test.channel",
            "loyalty_card_id": loyalty_card.id,
            "entry_id": entry.id,
        },
    )
    assert mock_send_message_to_hermes_payment.call_args_list[0][0] == (
        "post_payment_account",
        {
            "channel_slug": "com.test.channel",
            "user_id": user_id,
            "payment_account_id": payment_account_id,
            "auto_link": True,
            "created": True,
            "supersede": False,
        },
    )

    links = (
        db_session.query(PaymentAccountUserAssociation)
        .filter(
            PaymentAccountUserAssociation.payment_card_account_id == resp.json["payment_card"]["id"],
            PaymentAccountUserAssociation.user_id == user_id,
        )
        .count()
    )
    assert links == 1

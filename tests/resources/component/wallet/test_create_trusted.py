import typing
from base64 import b64encode
from collections.abc import Callable
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import falcon
import pytest
from sqlalchemy import func, select

from angelia.hermes.models import (
    Channel,
    PaymentAccount,
    PaymentAccountUserAssociation,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    User,
)
from tests.authentication.helpers.token_helpers import create_test_b2b_token
from tests.factories import (
    PaymentCardFactory,
    PaymentSchemeAccountAssociationFactory,
)
from tests.helpers.authenticated_request import get_client
from tests.resources.component.config import MockAuthConfig

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


def mock_token_request(path: str, method: str, body: dict, auth_token: str) -> falcon.testing.Result:
    return get_client().simulate_request(
        path=path,
        json=body,
        method=method,
        headers={"Authorization": auth_token},
    )


@dataclass
class Mocks:
    send_message_to_hermes_token: MagicMock
    send_message_to_hermes_payment: MagicMock
    send_message_to_hermes_loyalty: MagicMock
    send_message_to_hermes_middleware: MagicMock
    wallet_current_token_secret: MagicMock
    current_token_secret: MagicMock
    b2b_get_secret: MagicMock


@pytest.fixture(scope="function")
def create_trusted_payload() -> Callable[[int, str, str], dict]:
    def _payload(
        loyalty_plan_id: int, card_number: str, pcard_fingerprint: str = "b5fe350d5135ab64a8f3c1097fadefd9effb"
    ) -> dict:
        return {
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
                                "value": card_number,
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
                "fingerprint": pcard_fingerprint,
                "country": "GB",
                "currency_code": "GBP",
            },
        }

    return _payload


@pytest.fixture(scope="function")
def trusted_add_answer_fields(trusted_add_req_data: dict) -> None:
    """The account_id field in the request data is converted by the serializer into merchant_identifier.
    Since the data isn't serialized for these tests we need to do the conversion for the handler to process
    correctly.
    """
    answer_fields = trusted_add_req_data["account"]
    answer_fields["merchant_fields"] = {"merchant_identifier": answer_fields["merchant_fields"]["account_id"]}

    return answer_fields


@pytest.fixture(scope="function")
def mocks() -> "typing.Generator[Mocks, None, None]":
    with (
        patch("angelia.api.middleware.send_message_to_hermes") as send_message_to_hermes_middleware,
        patch("angelia.handlers.loyalty_card.send_message_to_hermes") as send_message_to_hermes_loyalty,
        patch("angelia.handlers.payment_account.send_message_to_hermes") as send_message_to_hermes_payment,
        patch("angelia.handlers.token.send_message_to_hermes") as send_message_to_hermes_token,
        patch("angelia.resources.wallet.get_current_token_secret") as wallet_current_token_secret,
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as b2b_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token_secret,
    ):
        yield Mocks(
            wallet_current_token_secret=wallet_current_token_secret,
            send_message_to_hermes_token=send_message_to_hermes_token,
            send_message_to_hermes_payment=send_message_to_hermes_payment,
            send_message_to_hermes_loyalty=send_message_to_hermes_loyalty,
            send_message_to_hermes_middleware=send_message_to_hermes_middleware,
            current_token_secret=current_token_secret,
            b2b_get_secret=b2b_get_secret,
        )


def test_on_post_create_trusted_201(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mocks: Mocks,
    create_trusted_payload: Callable[..., dict],
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
    mocks.wallet_current_token_secret.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key
    mocks.current_token_secret.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key
    mocks.b2b_get_secret.return_value = mock_auth_config.secrets_dict

    visa_card_number = "4234563200133540455525"

    assert db_session.scalar(select(func.count(SchemeAccount.id))) == 0

    payload = create_trusted_payload(loyalty_plan_id, visa_card_number)
    auth_token = create_test_b2b_token(mock_auth_config)
    resp = mock_token_request(
        path="/v2/wallet/create_trusted",
        method="POST",
        body=payload,
        auth_token=auth_token,
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
    assert mocks.send_message_to_hermes_loyalty.call_args_list[0][0] == (
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
    mocks.send_message_to_hermes_middleware.assert_not_called()
    assert mocks.send_message_to_hermes_loyalty.call_args_list[1][0] == (
        "loyalty_card_trusted_add_success_event",
        {
            "user_id": user_id,
            "channel_slug": "com.test.channel",
            "loyalty_card_id": loyalty_card.id,
            "entry_id": entry.id,
        },
    )
    assert mocks.send_message_to_hermes_payment.call_args_list[0][0] == (
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


def test_on_post_create_trusted_201_basic_auth(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mocks: Mocks,
    create_trusted_payload: Callable[..., dict],
) -> None:
    loyalty_plan, channel, _ = setup_plan_channel_and_user(slug="test-scheme", is_trusted_channel=True)
    channel.email_required = False
    db_session.flush()
    setup_questions(loyalty_plan)
    db_session.flush()
    visa = PaymentCardFactory(slug="visa")
    db_session.add(visa)
    db_session.commit()

    mock_auth_config = MockAuthConfig(channel=channel)
    mocks.wallet_current_token_secret.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

    assert db_session.scalar(select(func.count(SchemeAccount.id))) == 0

    payload = create_trusted_payload(loyalty_plan.id, "4234563200133540455525")
    payload["token"] = {
        "grant_type": "client_credentials",
        "username": "banana",
        "scope": ["user"],
    }
    auth_token = "basic " + b64encode(f"{channel.bundle_id}:{channel.client_application.secret}".encode()).decode()
    resp = mock_token_request(
        path="/v2/wallet/create_trusted",
        method="POST",
        body=payload,
        auth_token=auth_token,
    )
    assert resp.status == falcon.HTTP_201


def test_on_post_create_trusted_409_ubiquity_conflict(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    mocks: Mocks,
    create_trusted_payload: Callable[..., dict],
) -> None:
    visa_card_number = "4234563200133540455525"
    pcard_fingerprint = "b5fe350d5135ab64a8f3c1097fadefd9effb"
    loyalty_plan, channel, user = setup_plan_channel_and_user(slug="test-scheme", is_trusted_channel=True)
    user.external_id = "old_user_external_id"
    channel.email_required = False
    db_session.flush()
    loyalty_plan_id = loyalty_plan.id
    setup_questions(loyalty_plan)
    db_session.flush()
    visa = PaymentCardFactory(slug="visa")
    db_session.add(visa)

    pll_link = PaymentSchemeAccountAssociationFactory()
    db_session.flush()
    pll_link.scheme_account.scheme = loyalty_plan
    pll_link.payment_card_account.fingerprint = pcard_fingerprint

    db_session.commit()

    existing_scheme_account_id = pll_link.scheme_account_id
    existing_payment_account_id = pll_link.payment_card_account_id
    existing_user_id = user.id

    mock_auth_config = MockAuthConfig(channel=channel, external_id="new_user_external_id")
    mocks.wallet_current_token_secret.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key
    mocks.current_token_secret.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key
    mocks.b2b_get_secret.return_value = mock_auth_config.secrets_dict

    payload = create_trusted_payload(loyalty_plan_id, visa_card_number, pcard_fingerprint)
    auth_token = create_test_b2b_token(mock_auth_config)
    resp = mock_token_request(
        path="/v2/wallet/create_trusted",
        method="POST",
        body=payload,
        auth_token=auth_token,
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "You may encounter this conflict when a provided payment card is already linked "
        "to a different loyalty account. The new wallet will not be created.",
        "error_slug": "CONFLICT",
    }

    assert db_session.scalar(select(func.count(User.id)).where(User.id != existing_user_id)) == 0
    assert (
        db_session.scalar(select(func.count(SchemeAccount.id)).where(SchemeAccount.id != existing_scheme_account_id))
        == 0
    )
    assert (
        db_session.scalar(select(func.count(PaymentAccount.id)).where(PaymentAccount.id != existing_payment_account_id))
        == 0
    )

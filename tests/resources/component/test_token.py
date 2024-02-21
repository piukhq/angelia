from time import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import jwt
import pytest
from falcon import HTTP_200, HTTP_409, HTTP_500, HTTPUnauthorized, Response
from pytest_mock import MockerFixture
from sqlalchemy import func, select

from angelia.api.custom_error_handlers import (
    INVALID_CLIENT,
    INVALID_GRANT,
    INVALID_REQUEST,
    UNAUTHORISED_CLIENT,
    UNSUPPORTED_GRANT_TYPE,
)
from angelia.hermes.models import ServiceConsent, User
from tests.authentication.helpers.token_helpers import create_refresh_token, create_test_b2b_token
from tests.factories import ChannelFactory, ServiceConsentFactory, UserFactory
from tests.helpers.authenticated_request import get_client
from tests.resources.component.config import MockAuthConfig

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

wrong_public_key_rsa = """
-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAm6FHxSsi1uYppqqdCOkt
0X5wxkgDQ8YYrNQZFp9Bwcm0wFDTsYvzQ8aHI3x2jPcPZINiFjFWVsJ863HONj0p
hosKjG5GzF9ZZkINPQ3IFLPvsj3rIXxSGmDBPZMGe4e2Tp36wsEBl0WdnduwxNhI
T0Ig5iCP+eAsjGACGdp1mPvnPj59aLM2BOSAcO0HvUHRtVV+CudSwIh/cTDPafuJ
wy36o/EB19MyVvj4GaZArFzhPH7YUg+6Ysk5pujfzhwFH1QBpnw1PK8ftz+Zvi3f
cO0JsXsmBvZaNKgB2xF5e470U6yHpmaeS/DoYh8TmTL76yZ5J2ctp3dQfQvn54zm
DCtzLn1j0B1EickHx7IvnXYFQ/pxbRFk0I33ST3DP0Ln0iUie2Nal2gPBwueynlh
BBSpka0GLNGXfW0kyKYZh9Z7Kw3sUE2Vw6Hd7XB0gJ9NZJLKm5XokONpIoAOXwDl
kRU3vrJ8HVTziYEBEPza01pwLDtYrp5cqiliDLmbsjQVGcpYE5I5rqGprJm8nrTY
s2se67yD+ya3hJ3CQAmpx5hnWwfY2rHxM6wLmCHEBXm5UL5XYc1LPj/y8RXGDWL9
JG6jON8R/f+w6OID6xpQTjX/frk95rfdFy6AHzMiPvAm0PqKA9llh62gFUCLzclz
gNFPE3TGi6KFpXoIia89hXMCAwEAAQ==
-----END PUBLIC KEY-----
"""


def mock_token_req_body(grant_type: str, scope: list[str]) -> dict:
    return {
        "grant_type": grant_type,
        "scope": scope,
    }


def mock_token_request(body: dict, headers: dict) -> Response:
    return get_client().simulate_request(
        path="/v2/token",
        json=body,
        method="POST",
        headers=headers,
    )


@pytest.mark.parametrize(
    "req_body,expected_resp",
    [
        (
            {
                "grant_type": "invalid_grant",
                "scope": ["user"],
            },
            UNSUPPORTED_GRANT_TYPE,
        ),
        (
            {
                "grant_type": "b2b",
                "scope": [""],
            },
            INVALID_REQUEST,
        ),
        (
            {
                "grant_type": "b2b",
                "scope": ["invalid"],
            },
            INVALID_REQUEST,
        ),
        (
            {
                "invalid": "b2b",
                "scope": ["user"],
            },
            INVALID_REQUEST,
        ),
        (
            {
                "grant_type": "b2b",
                "invalid": ["user"],
            },
            INVALID_REQUEST,
        ),
        (
            {
                "grant_type": "b2b",
            },
            INVALID_REQUEST,
        ),
        (
            {
                "grant_type": "b2b",
                "scope": ["user", "another"],
            },
            INVALID_REQUEST,
        ),
    ],
)
def test_token_invalid_request_body(
    req_body: dict,
    expected_resp: tuple[str, str],
    mocker: "MockerFixture",
    db_session: "Session",
) -> None:
    # # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")
    channel = ChannelFactory()
    mock_auth_config = MockAuthConfig(channel=channel)
    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == expected_resp[0]

    assert resp.json == {"error": expected_resp[1]}


@pytest.mark.parametrize(
    "header,expected_resp",
    [
        (
            {},
            HTTPUnauthorized(title="No Authentication Header", code="UNAUTHORISED"),
        ),
        (
            {"Authorization": "BearerToken"},
            HTTPUnauthorized(
                title="B2B Client Token or Secret must be in 2 parts separated by a space",
                code="INVALID_TOKEN",
            ),
        ),
        (
            {"Authorization": "Invalid foo"},
            HTTPUnauthorized(
                title="B2B Client Token or Secret must have 'bearer' or 'basic' prefix",
                code="INVALID_TOKEN",
            ),
        ),
        (
            {"Authorization": "Bearer foo"},
            HTTPUnauthorized(title="Supplied token is invalid", code="INVALID_TOKEN"),
        ),
    ],
)
def test_token_unauthorized(
    header: dict,
    expected_resp: HTTPUnauthorized,
    mocker: "MockerFixture",
    db_session: "Session",
) -> None:
    # # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    channel = ChannelFactory()
    mock_auth_config = MockAuthConfig(channel=channel)
    db_session.commit()

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers=header,
        )

    assert resp.status == expected_resp.status

    assert resp.json == {"error_message": expected_resp.title, "error_slug": expected_resp.code}


def test_token_key_vault_no_public_key(
    mocker: "MockerFixture",
    db_session: "Session",
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(is_trusted=True)
    mock_auth_config = MockAuthConfig(channel=channel)
    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = None  # No public key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == UNAUTHORISED_CLIENT[0]

    assert resp.json == {"error": UNAUTHORISED_CLIENT[1]}


def test_token_invalid_jwt_auth_token_missing_sub_claim(
    mocker: "MockerFixture",
    db_session: "Session",
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(is_trusted=True)
    mock_auth_config = MockAuthConfig(channel=channel, external_id=None)  # external_id is the sub
    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == INVALID_REQUEST[0]

    assert resp.json == {"error": INVALID_REQUEST[1]}


def test_token_expired_jwt_signature(
    mocker: "MockerFixture",
    db_session: "Session",
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(is_trusted=True)
    mock_auth_config = MockAuthConfig(channel=channel)
    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config, expired=True)

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == INVALID_GRANT[0]

    assert resp.json == {"error": INVALID_GRANT[1]}


def test_token_invalid_jwt_signature(
    mocker: "MockerFixture",
    db_session: "Session",
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(is_trusted=True)
    mock_auth_config = MockAuthConfig(channel=channel, public_key=wrong_public_key_rsa)
    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == UNAUTHORISED_CLIENT[0]

    assert resp.json == {"error": UNAUTHORISED_CLIENT[1]}


def test_token_b2b_grant_new_user(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(is_trusted=True)
    mock_auth_config = MockAuthConfig(channel=channel)
    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    user_ids_before = db_session.execute(select(User.id)).scalars().all()
    consents_before = db_session.execute(select(ServiceConsent)).all()

    assert len(user_ids_before) == 0
    assert consents_before == []

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == HTTP_200
    user_ids_after = db_session.execute(select(User.id)).scalars().all()
    consents_after = db_session.execute(select(ServiceConsent)).all()

    assert len(user_ids_after) == 1
    assert consents_after

    mock_auth_config.user_id = user_ids_after[0]
    mock_token_gen = mock_auth_config.mock_token_gen(db_session)

    assert resp.json == {
        "access_token": mock_token_gen.create_access_token(),
        "token_type": "bearer",
        "expires_in": mock_token_gen.access_life_time,
        "refresh_token": mock_token_gen.create_refresh_token(),
        "scope": req_body["scope"],
    }

    # Validate token
    decoded_token = jwt.decode(resp.json["access_token"], mock_auth_config.access_secret_key, algorithms=["HS512"])

    for claim in ("sub", "channel", "is_tester", "is_trusted_channel", "iat", "exp"):
        assert claim in decoded_token

    assert decoded_token["is_trusted_channel"] is True
    assert len(decoded_token) == 6


def test_token_b2b_grant_existing_user(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory()
    mock_auth_config = MockAuthConfig(channel=channel)
    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.commit()
    mock_auth_config.user_id = user.id
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    users_before = db_session.execute(select(User)).scalars().all()
    consents_before = db_session.execute(select(ServiceConsent)).all()
    assert len(users_before) == 1

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == HTTP_200
    users_after = db_session.execute(select(User)).scalars().all()
    consents_after = db_session.execute(select(ServiceConsent)).all()

    assert len(users_after) == 1
    assert users_before[0].uid == users_after[0].uid
    assert consents_after == consents_before

    mock_token_gen = mock_auth_config.mock_token_gen(db_session)

    assert resp.json == {
        "access_token": mock_token_gen.create_access_token(),
        "token_type": "bearer",
        "expires_in": mock_token_gen.access_life_time,
        "refresh_token": mock_token_gen.create_refresh_token(),
        "scope": req_body["scope"],
    }


def test_token_b2b_grant_new_user_optional_email(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="")

    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    user_ids_before = db_session.execute(select(User.id)).scalars().all()
    consents = db_session.scalar(select(func.count(ServiceConsent.user_id)))
    assert len(user_ids_before) == 0
    assert consents == 0

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == HTTP_200
    user_ids_after = db_session.execute(select(User.id)).scalars().all()
    consents = db_session.scalar(select(func.count(ServiceConsent.user_id)))
    assert len(user_ids_after) == 1
    assert consents == 1

    mock_auth_config.user_id = user_ids_after[0]
    mock_token_gen = mock_auth_config.mock_token_gen(db_session)

    assert resp.json == {
        "access_token": mock_token_gen.create_access_token(),
        "token_type": "bearer",
        "expires_in": mock_token_gen.access_life_time,
        "refresh_token": mock_token_gen.create_refresh_token(),
        "scope": req_body["scope"],
    }


def test_token_b2b_grant_existing_user_optional_email(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    ServiceConsentFactory(user_id=user.id)
    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    users = db_session.scalar(select(func.count(User.id)))
    consents = db_session.scalar(select(func.count(ServiceConsent.user_id)))
    assert users == 1
    assert consents == 1

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == HTTP_200
    users = db_session.scalar(select(func.count(User.id)))
    consents = db_session.scalar(select(func.count(ServiceConsent.user_id)))
    assert users == 1
    assert consents == 1

    mock_token_gen = mock_auth_config.mock_token_gen(db_session)

    assert resp.json == {
        "access_token": mock_token_gen.create_access_token(),
        "token_type": "bearer",
        "expires_in": mock_token_gen.access_life_time,
        "refresh_token": mock_token_gen.create_refresh_token(),
        "scope": req_body["scope"],
    }


@pytest.mark.parametrize(
    "invalid_email,expected_resp",
    [
        ("bonk", INVALID_GRANT),
        ("wrong_email@example.com", INVALID_CLIENT),
    ],
)
def test_token_b2b_grant_existing_user_invalid_email(
    invalid_email: str,
    expected_resp: tuple[str, str],
    mocker: "MockerFixture",
    db_session: "Session",
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory()
    mock_auth_config = MockAuthConfig(channel=channel)

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    ServiceConsentFactory(user_id=user.id)
    db_session.commit()

    assert user.email == mock_auth_config.email
    # Set wrong email for b2b token
    mock_auth_config.email = invalid_email
    assert user.email != mock_auth_config.email
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    users = db_session.scalar(select(func.count(User.id)))
    consents = db_session.scalar(select(func.count(ServiceConsent.user_id)))
    assert users == 1
    assert consents == 1

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == expected_resp[0]
    assert resp.json == {"error": expected_resp[1]}


def test_token_b2b_grant_existing_user_required_email_missing(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=True)
    mock_auth_config = MockAuthConfig(channel=channel)

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    ServiceConsentFactory(user_id=user.id)
    db_session.commit()

    assert user.email == mock_auth_config.email
    # Set wrong email for b2b token
    mock_auth_config.email = None
    assert user.email != mock_auth_config.email
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    users = db_session.scalar(select(func.count(User.id)))
    consents = db_session.scalar(select(func.count(ServiceConsent.user_id)))
    assert users == 1
    assert consents == 1

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == INVALID_GRANT[0]


def test_token_b2b_grant_channel_bundle_id_not_found(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory()
    mock_auth_config = MockAuthConfig(channel=channel)
    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_auth_config.channel.bundle_id = "wrong.bundle.id"
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == UNAUTHORISED_CLIENT[0]

    assert resp.json == {"error": UNAUTHORISED_CLIENT[1]}


def test_token_b2b_grant_conflicting_user_channel_data(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory()
    mock_auth_config = MockAuthConfig(channel=channel)
    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email="another@email.com",
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == HTTP_409

    assert resp.json == {"error_message": HTTP_409, "error_slug": "CONFLICT"}


def test_create_access_token_refresh_grant(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == HTTP_200

    decoded_token = jwt.decode(resp.json["access_token"], mock_auth_config.access_secret_key, algorithms=["HS512"])

    for claim in ("sub", "channel", "is_tester", "is_trusted_channel", "iat", "exp"):
        assert claim in decoded_token

    assert len(decoded_token) == 6


def test_create_access_token_refresh_grant_inactive_user(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
        is_active=False,  # Inactive user
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == UNAUTHORISED_CLIENT[0]

    assert resp.json == {"error": UNAUTHORISED_CLIENT[1]}


def test_create_access_token_refresh_grant_user_no_longer_exists(
    mocker: "MockerFixture", db_session: "Session"
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "sub": 1,  # non existent user_id
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == HTTP_500

    assert resp.json == {"error_message": HTTP_500, "error_slug": "INTERNAL_SERVER_ERROR"}


def test_create_access_token_refresh_grant_channel_bundle_id_not_found(
    mocker: "MockerFixture", db_session: "Session"
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": "wrong.bundle.id",  # Wrong bundle id
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == HTTP_500

    assert resp.json == {"error_message": HTTP_500, "error_slug": "INTERNAL_SERVER_ERROR"}


def test_create_refresh_token_b2b_grant(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="b2b")
    db_session.commit()
    test_b2b_token = create_test_b2b_token(auth_config=mock_auth_config)

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("b2b", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": test_b2b_token},
        )

    assert resp.status == HTTP_200

    decoded_token = jwt.decode(resp.json["refresh_token"], mock_auth_config.access_secret_key, algorithms=["HS512"])

    for claim in ("sub", "channel", "client_id", "grant_type", "external_id", "iat", "exp"):
        assert claim in decoded_token

    assert len(decoded_token) == 7


def test_create_refresh_token_refresh_grant(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == HTTP_200

    decoded_token = jwt.decode(resp.json["refresh_token"], mock_auth_config.access_secret_key, algorithms=["HS512"])

    for claim in ("sub", "channel", "client_id", "grant_type", "external_id", "iat", "exp"):
        assert claim in decoded_token

    assert len(decoded_token) == 7


def test_token_refresh_grant_invalid_prefix_kid(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"invalid-{mock_auth_config.access_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == INVALID_REQUEST[0]

    assert resp.json == {"error": INVALID_REQUEST[1]}


def test_token_refresh_grant_illegal_kid_security_check(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    db_session.commit()

    illegal_post_fix_kid = "current_key"

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{illegal_post_fix_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        mock_get_secret.return_value = mock_auth_config.secrets_dict
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    expected_error_resp = HTTPUnauthorized(title="illegal KID", code="INVALID_TOKEN")

    assert resp.status == expected_error_resp.status

    assert resp.json == {"error_message": expected_error_resp.title, "error_slug": expected_error_resp.code}


def test_create_refresh_token_refresh_grant_missing_client_id_claim(
    mocker: "MockerFixture", db_session: "Session"
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": mock_auth_config.channel_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == INVALID_GRANT[0]

    assert resp.json == {"error": INVALID_GRANT[1]}


def test_create_refresh_token_refresh_grant_missing_sub_claim(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == INVALID_REQUEST[0]

    assert resp.json == {"error": INVALID_REQUEST[1]}


@pytest.mark.parametrize(
    "test_name,mock_secret",
    [
        (
            "invalid_key",
            False,
        ),
        (
            "invalid_secret",
            "my_secret_bad",
        ),
    ],
)
def test_create_access_token_refresh_grant_invalid(
    test_name: str, mock_secret: bool | str, mocker: "MockerFixture", db_session: "Session"
) -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_secret
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == UNAUTHORISED_CLIENT[0]

    assert resp.json == {"error": UNAUTHORISED_CLIENT[1]}


def test_create_access_token_refresh_grant_expired_auth_token(mocker: "MockerFixture", db_session: "Session") -> None:
    # Mock hermes message
    mocker.patch("angelia.handlers.loyalty_card.send_message_to_hermes")

    # Mock time used for token expiry
    mock_time = mocker.patch("angelia.handlers.token.time")
    mock_time.return_value = time()

    channel = ChannelFactory(email_required=False)
    mock_auth_config = MockAuthConfig(channel=channel, email="", grant_type="refresh_token")

    # Create user
    user = UserFactory(
        client=mock_auth_config.channel.client_application,
        external_id=mock_auth_config.external_id,
        email=mock_auth_config.email,
    )
    db_session.flush()
    mock_auth_config.user_id = user.id
    db_session.commit()

    auth_token = create_refresh_token(
        mock_auth_config.access_kid,
        {mock_auth_config.access_kid: mock_auth_config.access_secret_key},
        f"refresh-{mock_auth_config.access_kid}",
        {
            "sub": mock_auth_config.user_id,
            "channel": mock_auth_config.channel_id,
            "client_id": mock_auth_config.channel.client_id,
            "grant_type": "b2b",
            "external_id": mock_auth_config.external_id,
        },
        expired=True,
    )

    # Patch secrets loaders
    with (
        patch("angelia.api.auth.get_access_token_secret") as access_token_secret,
        patch("angelia.resources.token.get_current_token_secret") as current_token,
    ):
        access_token_secret.return_value = mock_auth_config.access_secret_key
        current_token.return_value = mock_auth_config.access_kid, mock_auth_config.access_secret_key

        req_body = mock_token_req_body("refresh_token", ["user"])

        resp = mock_token_request(
            body=req_body,
            headers={"Authorization": auth_token},
        )

    assert resp.status == INVALID_GRANT[0]

    assert resp.json == {"error": INVALID_GRANT[1]}

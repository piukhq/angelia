from base64 import b64encode
from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import ANY, MagicMock

import pytest
from pytest_mock import MockerFixture

from tests.factories import ChannelFactory
from tests.helpers.authenticated_request import get_client

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from angelia.hermes.models import Channel


@dataclass
class Mocks:
    mock_token_gen: MagicMock
    mock_get_current_token_secret: MagicMock


@pytest.fixture(scope="function")
def channel(db_session: "Session") -> "Channel":
    channel = ChannelFactory(email_required=False)
    db_session.flush()
    return channel


@pytest.fixture(scope="function")
def mocks(mocker: MockerFixture) -> Mocks:
    mock_get_current_token_secret = mocker.patch("angelia.resources.token.get_current_token_secret")
    mock_token_gen = mocker.patch("angelia.resources.token.TokenGen")
    mock_token_gen.return_value.create_access_token.return_value = "sample access token"
    mock_token_gen.return_value.create_refresh_token.return_value = "sample refresh token"
    mock_token_gen.return_value.access_life_time = 600
    return Mocks(mock_token_gen, mock_get_current_token_secret)


def test_basic_auth_ok(channel: "Channel", mocks: Mocks) -> None:
    mocks.mock_get_current_token_secret.return_value = ("foo", "bar")
    client_secret = str(channel.client_application.secret)
    bundle_id = channel.bundle_id

    headers = {"Authorization": "basic " + b64encode(f"{bundle_id}:{client_secret}".encode()).decode()}
    payload = {
        "grant_type": "client_credentials",
        "username": "banana",
        "scope": ["user"],
    }

    resp = get_client().simulate_post("/v2/token", json=payload, headers=headers)

    assert resp.status_code == 200, resp.json
    mocks.mock_token_gen.assert_called_once_with(
        db_session=ANY,
        external_user_id=payload["username"],
        channel_id=bundle_id,
        access_kid="foo",
        access_secret_key="bar",
        grant_type=payload["grant_type"],
        scope=[],
    )


def test_basic_auth_invalid_token_401(channel: "Channel", mocks: Mocks) -> None:
    client_secret = str(channel.client_application.secret)
    bundle_id = channel.bundle_id
    payload = {
        "grant_type": "client_credentials",
        "username": "banana",
        "scope": [
            "user",
        ],
    }

    for wrong_auth_type, expected_error_message in (
        ("not_encoded_auth", "Supplied token is invalid"),
        ("wrong_prefix", "B2B Client Token or Secret must have 'bearer' or 'basic' prefix"),
        ("missing_prefix", "B2B Client Token or Secret must be in 2 parts separated by a space"),
    ):
        match wrong_auth_type:
            case "not_encoded_auth":
                headers = {"Authorization": f"basic {bundle_id}:{client_secret}"}
            case "wrong_prefix":
                headers = {"Authorization": "jeff " + b64encode(f"{bundle_id}:{client_secret}".encode()).decode()}
            case "missing_prefix":
                headers = {"Authorization": b64encode(f"{bundle_id}:{client_secret}".encode()).decode()}

        resp = get_client().simulate_post("/v2/token", json=payload, headers=headers)

        assert resp.status_code == 401, wrong_auth_type
        assert resp.json == {"error_message": expected_error_message, "error_slug": "INVALID_TOKEN"}, wrong_auth_type
        mocks.mock_get_current_token_secret.assert_not_called()
        mocks.mock_token_gen.assert_not_called()


def test_basic_auth_invalid_request_400(channel: "Channel", mocks: Mocks) -> None:
    client_secret = str(channel.client_application.secret)
    bundle_id = channel.bundle_id
    headers = {"Authorization": "basic " + b64encode(f"{bundle_id}:{client_secret}".encode()).decode()}
    payload = {
        "grant_type": "client_credentials",
        "username": "banana",
        "scope": ["user"],
    }

    for error_type in (
        "missing_username",
        "missing_grant",
        "wrong_grant",
        "missing_scope",
        "wrong_scope",
        "extra_field",
        "wrong_bundle",
        "wrong_secret",
    ):
        match error_type:
            case "missing_username":
                payload = {
                    "grant_type": "client_credentials",
                    "scope": ["user"],
                }
            case "missing_grant":
                payload = {
                    "username": "banana",
                    "scope": ["user"],
                }
            case "wrong_grant":
                payload = {
                    "grant_type": "jeff",
                    "username": "banana",
                    "scope": ["user"],
                }
            case "missing_scope":
                payload = {
                    "grant_type": "client_credentials",
                    "username": "banana",
                }
            case "wrong_scope":
                payload = {
                    "grant_type": "client_credentials",
                    "username": "banana",
                    "scope": ["jeff"],
                }
            case "extra_field":
                payload = {
                    "grant_type": "client_credentials",
                    "username": "banana",
                    "scope": ["user"],
                    "hotel": "trivago",
                }
            case "wrong_bundle":
                headers = {"Authorization": "basic " + b64encode(f"jeff:{client_secret}".encode()).decode()}
            case "wrong_secret":
                headers = {"Authorization": "basic " + b64encode(f"{bundle_id}:jeff".encode()).decode()}

        resp = get_client().simulate_post("/v2/token", json=payload, headers=headers)

        assert resp.status_code == 400, error_type
        assert resp.json == {"error": "invalid_request"}, error_type
        mocks.mock_get_current_token_secret.assert_not_called()
        mocks.mock_token_gen.assert_not_called()

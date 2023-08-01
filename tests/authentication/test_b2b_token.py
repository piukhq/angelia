import datetime
from unittest.mock import MagicMock, patch

import azure.core.exceptions
import jwt
import pytest

from app.api.auth import (
    ClientToken,
    get_authenticated_external_channel,
    get_authenticated_external_user,
    get_authenticated_external_user_email,
)
from app.api.custom_error_handlers import TokenHTTPError
from app.api.helpers import vault
from app.api.helpers.vault import load_secrets_from_vault

from .helpers.test_jwtRS512 import private_key, public_key, wrong_public_key
from .helpers.token_helpers import create_b2b_token, validate_mock_request


class TestB2BAuth:
    channel: str
    external_id: str
    email: str
    secrets_dict: dict[str, str]

    @classmethod
    def setup_class(cls) -> None:
        cls.channel = "com.test.channel"
        cls.external_id = "testme"
        cls.email = "customer1@test.com"
        cls.secrets_dict = {"key": public_key, "channel": cls.channel}

    def test_public_private_keys_are_valid(self) -> None:
        test_jwt = jwt.encode({"x": 1}, key=private_key, algorithm="RS512")
        test = jwt.decode(test_jwt, key=public_key, algorithms=["RS512"])
        assert test["x"] == 1

    def test_load_secrets_from_vault_azure(self) -> None:
        with patch("app.api.helpers.vault.get_azure_client") as mock_get_client:
            key = '{"public_key": "blabla"}'

            def get_secret(_: str) -> MagicMock:
                _get_secret = MagicMock()
                _get_secret.value = key
                return _get_secret

            mock_get_client.return_value.get_secret.side_effect = get_secret
            loaded = load_secrets_from_vault(["test-1"], was_loaded=False, allow_reload=True)
            assert loaded
            assert vault._local_vault_store.get("test-1") == {"public_key": "blabla"}
            vault._local_vault_store = {}

    def test_load_secrets_from_vault_azure_fail(self) -> None:
        with patch("app.api.helpers.vault.get_azure_client") as mock_get_client:
            mock_get_client.return_value.get_secret.side_effect = azure.core.exceptions.ResourceNotFoundError

            loaded = load_secrets_from_vault(["test-1"], was_loaded=False, allow_reload=True)

            assert not loaded

    def test_auth_valid(self) -> None:
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict
            auth_token = create_b2b_token(private_key, sub=self.external_id, kid="test-1", email=self.email)
            mock_request = validate_mock_request(
                auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]}
            )
            assert get_authenticated_external_channel(mock_request) == self.channel
            assert get_authenticated_external_user(mock_request) == self.external_id
            assert get_authenticated_external_user_email(mock_request) == self.email

    def test_auth_valid_optional_email(self) -> None:
        auth_token_with_claim = create_b2b_token(private_key, sub=self.external_id, kid="test-1", email="")
        auth_token_without_claim = create_b2b_token(private_key, sub=self.external_id, kid="test-1")
        auth_token_with_null_claim = create_b2b_token(
            private_key, sub=self.external_id, kid="test-1", email=None, allow_none=True
        )

        for auth_token in (auth_token_with_claim, auth_token_without_claim, auth_token_with_null_claim):
            with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
                mock_get_secret.return_value = self.secrets_dict
                mock_request = validate_mock_request(
                    auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]}
                )
                assert get_authenticated_external_channel(mock_request) == self.channel
                assert get_authenticated_external_user(mock_request) == self.external_id
                assert get_authenticated_external_user_email(mock_request, email_required=False) == ""

    def test_auth_invalid_secret(self) -> None:
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = False
            try:
                auth_token = create_b2b_token(private_key, sub=self.external_id, kid="test-1", email=self.email)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                raise AssertionError("Did not detect the invalid key")
            except TokenHTTPError as e:
                assert e.error == "unauthorized_client"
                assert e.status == "400"
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    def test_auth_invalid_key(self) -> None:
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            secrets_dict = {"key": wrong_public_key, "channel": self.channel}
            mock_get_secret.return_value = secrets_dict
            try:
                auth_token = create_b2b_token(private_key, sub=self.external_id, kid="test-1", email=self.email)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                raise AssertionError("Did not detect invalid key")
            except TokenHTTPError as e:
                assert e.error == "unauthorized_client"
                assert e.status == "400"
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    def test_auth_time_out(self) -> None:
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict
            try:
                auth_token = create_b2b_token(
                    private_key,
                    sub=self.external_id,
                    kid="test-1",
                    email=self.email,
                    utc_now=datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(seconds=500),
                )
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                raise AssertionError("Did not detect time out")
            except TokenHTTPError as e:
                assert e.error == "invalid_grant"
                assert e.status == "400"
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    def test_missing_sub_claim(self) -> None:
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict
            try:
                auth_token = create_b2b_token(private_key, sub=None, kid="test-1", email=self.email)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                raise AssertionError("Did not detect missing sub claim")
            except TokenHTTPError as e:
                assert e.error == "invalid_request"
                assert e.status == "400"
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    @pytest.mark.parametrize("email_required", [True, False])
    @pytest.mark.parametrize("email", ["bonk", False])
    def test_process_b2b_token_invalid_email(self, email: str, email_required: bool) -> None:
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict
            auth_token = create_b2b_token(private_key, sub=self.external_id, kid="test-1", email=email)
            mock_request = validate_mock_request(
                auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]}
            )

            with pytest.raises(TokenHTTPError) as e:
                get_authenticated_external_user_email(mock_request, email_required=email_required)

            assert e.value.error == "invalid_grant"
            assert e.value.status == "400"

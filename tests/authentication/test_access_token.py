import datetime
from unittest.mock import patch

import falcon

from app.api.auth import AccessToken, get_authenticated_channel, get_authenticated_user

from .helpers.token_helpers import create_access_token, validate_mock_request


class TestAccessAuth:
    secrets_dict: dict[str, str]
    sub: int
    channel: str

    @classmethod
    def setup_class(cls) -> None:
        cls.secrets_dict = {"test_key-1": "my_secret_1"}
        cls.sub = 39624
        cls.channel = "com_bink.wallet"

    def test_auth_valid(self) -> None:
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            test_secret_key = "test_key-1"
            mock_get_secret.return_value = self.secrets_dict.get(test_secret_key)
            auth_token = create_access_token(test_secret_key, self.secrets_dict, self.sub, self.channel)
            mock_request = validate_mock_request(auth_token, AccessToken)
            assert get_authenticated_user(mock_request) == self.sub
            assert get_authenticated_channel(mock_request) == self.channel

    def test_auth_invalid_key(self) -> None:
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = False
            try:
                auth_token = create_access_token("test_key-1", self.secrets_dict, self.sub, self.channel)
                validate_mock_request(auth_token, AccessToken)
                raise AssertionError("Did not detect invalid key")
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token has unknown secret"
                assert e.code == "INVALID_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    def test_auth_invalid_secret(self) -> None:
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = "my_secret_bad"
            try:
                auth_token = create_access_token("test_key-1", self.secrets_dict, self.sub, self.channel)
                validate_mock_request(auth_token, AccessToken)
                raise AssertionError("Did not detect invalid key")
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token signature error: Signature verification failed"
                assert e.code == "INVALID_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    def test_auth_time_out(self) -> None:
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            test_secret_key = "test_key-1"
            mock_get_secret.return_value = self.secrets_dict.get(test_secret_key)
            try:
                auth_token = create_access_token(
                    test_secret_key,
                    self.secrets_dict,
                    self.sub,
                    self.channel,
                    utc_now=datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(seconds=500),
                )
                validate_mock_request(auth_token, AccessToken)
                raise AssertionError("Did not detect time out")
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token expired: Signature has expired"
                assert e.code == "EXPIRED_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    def test_missing_sub_claim(self) -> None:
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            test_secret_key = "test_key-1"
            mock_get_secret.return_value = self.secrets_dict.get(test_secret_key)
            try:
                auth_token = create_access_token(test_secret_key, self.secrets_dict, channel=self.channel)
                mock_request = validate_mock_request(auth_token, AccessToken)
                assert get_authenticated_user(mock_request) == self.sub
                assert get_authenticated_channel(mock_request) == self.channel
                raise AssertionError("Did not detect missing sub claim")
            except falcon.HTTPUnauthorized as e:
                assert e.code == "MISSING_CLAIM"
                assert e.title == "Access Token has missing claim"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    def test_missing_channel_claim(self) -> None:
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            test_secret_key = "test_key-1"
            mock_get_secret.return_value = self.secrets_dict.get(test_secret_key)
            try:
                auth_token = create_access_token(test_secret_key, self.secrets_dict, sub=self.sub)
                mock_request = validate_mock_request(auth_token, AccessToken)
                assert get_authenticated_user(mock_request) == self.sub
                assert get_authenticated_channel(mock_request) == self.channel
                raise AssertionError("Did not detect missing channel claim")
            except falcon.HTTPUnauthorized as e:
                assert e.code == "MISSING_CLAIM"
                assert e.title == "Access Token has missing claim"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

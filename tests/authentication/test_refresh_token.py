import datetime
from copy import copy
from unittest.mock import patch

from app.api.auth import (
    ClientToken,
    get_authenticated_external_channel,
    get_authenticated_token_client,
    get_authenticated_token_user,
)
from app.api.custom_error_handlers import TokenHTTPError

from .helpers.token_helpers import create_refresh_token, validate_mock_request


class TestRefreshAuth:
    @classmethod
    def setup_class(cls):
        cls.secrets_dict = {"test_key-1": "my_secret_1"}
        cls.payload = {
            "sub": 39624,
            "channel": "com.test.wallet",
            "client_id": "dv18jwdwoFhjklsdvzxcPQslovceTQWBWEVlwdFGHikkkwdfff34wefw2zXAKlz",
            "grant_type": "b2b",
            "external_id": "test_user",
        }
        base_key = "test_key-1"
        cls.test_secret_key = f"refresh-{base_key}"  # refresh token must be prefixed with "refresh-"
        cls.base_key = base_key

    def test_auth_valid(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict.get(self.base_key)
            auth_token = create_refresh_token(self.base_key, self.secrets_dict, self.test_secret_key, self.payload)
            mock_request = validate_mock_request(
                auth_token, ClientToken, media={"grant_type": "refresh_token", "scope": ["user"]}
            )
            assert get_authenticated_token_user(mock_request) == self.payload["sub"]
            assert get_authenticated_external_channel(mock_request) == self.payload["channel"]

    def test_auth_invalid_key(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = False
            try:
                auth_token = create_refresh_token(self.base_key, self.secrets_dict, self.test_secret_key, self.payload)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "refresh_token", "scope": ["user"]})
                assert False, "Did not detect the invalid key"
            except TokenHTTPError as e:
                assert e.error == "unauthorized_client"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_auth_invalid_secret(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = "my_secret_bad"
            try:
                auth_token = create_refresh_token(self.base_key, self.secrets_dict, self.test_secret_key, self.payload)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "refresh_token", "scope": ["user"]})
                assert False, "Did not detect invalid key"
            except TokenHTTPError as e:
                assert e.error == "unauthorized_client"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_auth_time_out(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict.get(self.base_key)
            try:
                auth_token = create_refresh_token(
                    self.base_key,
                    self.secrets_dict,
                    self.test_secret_key,
                    self.payload,
                    utc_now=datetime.datetime.utcnow() - datetime.timedelta(seconds=500),
                )
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "refresh_token", "scope": ["user"]})
                assert False, "Did not detect time out"
            except TokenHTTPError as e:
                assert e.error == "invalid_grant"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_missing_sub_claim(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict.get(self.base_key)
            try:
                payload = copy(self.payload)
                del payload["sub"]
                auth_token = create_refresh_token(self.base_key, self.secrets_dict, self.test_secret_key, payload)
                mock_request = validate_mock_request(
                    auth_token, ClientToken, media={"grant_type": "refresh_token", "scope": ["user"]}
                )
                assert get_authenticated_token_user(mock_request) == self.payload["sub"]
                assert False, "Did not detect missing sub claim"
            except TokenHTTPError as e:
                assert e.error == "invalid_request"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_missing_client_id_claim(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict.get(self.base_key)
            try:
                payload = copy(self.payload)
                del payload["client_id"]
                auth_token = create_refresh_token(self.base_key, self.secrets_dict, self.test_secret_key, payload)
                mock_request = validate_mock_request(
                    auth_token, ClientToken, media={"grant_type": "refresh_token", "scope": ["user"]}
                )
                assert get_authenticated_token_user(mock_request) == self.payload["sub"]
                assert get_authenticated_token_client(mock_request) == self.payload["client_id"]
                assert False, "Did not detect missing channel claim"
            except TokenHTTPError as e:
                assert e.error == "invalid_grant"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

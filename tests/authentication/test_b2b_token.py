import datetime
from unittest.mock import patch

import jwt

from app.api.auth import (
    ClientToken,
    get_authenticated_external_channel,
    get_authenticated_external_user,
    get_authenticated_external_user_email,
)
from app.api.custom_error_handlers import TokenHTTPError

from .helpers.test_jwtRS512 import private_key, public_key, wrong_public_key
from .helpers.token_helpers import create_b2b_token, validate_mock_request


class TestB2BAuth:
    @classmethod
    def setup_class(cls):
        channel = "com.test.channel"
        cls.channel = channel
        cls.external_id = "testme"
        cls.email = "customer1@test.com"
        cls.secrets_dict = {"key": public_key, "channel": channel}

    def test_public_private_keys_are_valid(self):
        test_jwt = jwt.encode({"x": 1}, key=private_key, algorithm="RS512")
        test = jwt.decode(test_jwt, key=public_key, algorithms="RS512")
        assert test["x"] == 1

    def test_auth_valid(self):
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict
            auth_token = create_b2b_token(private_key, sub=self.external_id, kid="test-1", email=self.email)
            mock_request = validate_mock_request(
                auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]}
            )
            assert get_authenticated_external_channel(mock_request) == self.channel
            assert get_authenticated_external_user(mock_request) == self.external_id
            assert get_authenticated_external_user_email(mock_request) == self.email

    def test_auth_invalid_key(self):
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = False
            try:
                auth_token = create_b2b_token(private_key, sub=self.external_id, kid="test-1", email=self.email)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                assert False, "Did not detect the invalid key"
            except TokenHTTPError as e:
                assert e.error == "unauthorized_client"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_auth_invalid_secret(self):
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            secrets_dict = {"key": wrong_public_key, "channel": self.channel}
            mock_get_secret.return_value = secrets_dict
            try:
                auth_token = create_b2b_token(private_key, sub=self.external_id, kid="test-1", email=self.email)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                assert False, "Did not detect invalid key"
            except TokenHTTPError as e:
                assert e.error == "unauthorized_client"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_auth_time_out(self):
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict
            try:
                auth_token = create_b2b_token(
                    private_key,
                    sub=self.external_id,
                    kid="test-1",
                    email=self.email,
                    utc_now=datetime.datetime.utcnow() - datetime.timedelta(seconds=500),
                )
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                assert False, "Did not detect time out"
            except TokenHTTPError as e:
                assert e.error == "invalid_grant"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_missing_sub_claim(self):
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = self.secrets_dict
            try:
                auth_token = create_b2b_token(private_key, sub=None, kid="test-1", email=self.email)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                assert False, "Did not detect missing sub claim"
            except TokenHTTPError as e:
                assert e.error == "invalid_request"
                assert e.status == "400"
            except Exception as e:
                assert False, f"Exception in code or test {e}"

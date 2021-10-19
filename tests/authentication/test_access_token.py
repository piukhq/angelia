import datetime
from unittest.mock import patch

import falcon
from app.api.custom_error_handlers import TokenHTTPError

from app.api.auth import AccessToken, get_authenticated_channel, get_authenticated_user

from .helpers.token_helpers import create_access_token, validate_mock_request


class TestAccessAuth:
    @classmethod
    def setup_class(cls):
        cls.secrets_dict = {"test_key-1": "my_secret_1"}
        cls.sub = 39624
        cls.channel = "com_bink.wallet"

    def test_auth_valid(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            test_secret_key = "test_key-1"
            mock_get_secret.return_value = self.secrets_dict.get(test_secret_key)
            auth_token = create_access_token(test_secret_key, self.secrets_dict, self.sub, self.channel)
            mock_request = validate_mock_request(auth_token, AccessToken)
            assert get_authenticated_user(mock_request) == self.sub
            assert get_authenticated_channel(mock_request) == self.channel

    def test_auth_invalid_key(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = False
            try:
                auth_token = create_access_token("test_key-1", self.secrets_dict, self.sub, self.channel)
                validate_mock_request(auth_token, AccessToken)
                assert False, "Did not detect invalid key"
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token has unknown secret"
                assert e.code == "INVALID_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_auth_invalid_secret(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            mock_get_secret.return_value = "my_secret_bad"
            try:
                auth_token = create_access_token("test_key-1", self.secrets_dict, self.sub, self.channel)
                validate_mock_request(auth_token, AccessToken)
                assert False, "Did not detect invalid key"
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token signature error: Signature verification failed"
                assert e.code == "INVALID_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_auth_time_out(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            test_secret_key = "test_key-1"
            mock_get_secret.return_value = self.secrets_dict.get(test_secret_key)
            try:
                auth_token = create_access_token(
                    test_secret_key,
                    self.secrets_dict,
                    self.sub,
                    self.channel,
                    utc_now=datetime.datetime.utcnow() - datetime.timedelta(seconds=500),
                )
                validate_mock_request(auth_token, AccessToken)
                assert False, "Did not detect time out"
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token expired: Signature has expired"
                assert e.code == "EXPIRED_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_missing_sub_claim(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            test_secret_key = "test_key-1"
            mock_get_secret.return_value = self.secrets_dict.get(test_secret_key)
            try:
                auth_token = create_access_token(test_secret_key, self.secrets_dict, channel=self.channel)
                mock_request = validate_mock_request(auth_token, AccessToken)
                assert get_authenticated_user(mock_request) == self.sub
                assert get_authenticated_channel(mock_request) == self.channel
                assert False, "Did not detect missing sub claim"
            except falcon.HTTPUnauthorized as e:
                assert e.code == "MISSING_CLAIM"
                assert e.title == 'Access Token has missing claim'
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_missing_channel_claim(self):
        with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
            test_secret_key = "test_key-1"
            mock_get_secret.return_value = self.secrets_dict.get(test_secret_key)
            try:
                auth_token = create_access_token(test_secret_key, self.secrets_dict, sub=self.sub)
                mock_request = validate_mock_request(auth_token, AccessToken)
                assert get_authenticated_user(mock_request) == self.sub
                assert get_authenticated_channel(mock_request) == self.channel
                assert False, "Did not detect missing channel claim"
            except falcon.HTTPUnauthorized as e:
                assert e.code == "MISSING_CLAIM"
                assert e.title == "Access Token has missing claim"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

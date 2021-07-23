import falcon
import jwt
import datetime
from unittest.mock import Mock, patch
from app.api.auth import AccessToken, get_authenticated_user, get_authenticated_channel


class MockContext:
    auth_obj = AccessToken()
    auth_instance = auth_obj


def setup_mock_request(auth_header):
    """
    Makes a mock request object which holds the relevant data just like falcon.request
    Sets the mock context up in same way as middleware does setting
    context.auth_instance to an instance of AccessToken

    :param auth_header:
    :return: mock_request
    """
    mock_request = Mock(spec=falcon.Request)
    mock_request.context = MockContext
    mock_request.auth = auth_header
    return mock_request


def validate_mock_request(auth_token):
    """
    Sets up request object and with authentication object as middleware

    :param auth_token:
    :return: mock_request
    """
    mock_request = setup_mock_request(auth_token)
    auth_obj = mock_request.context.auth_instance
    auth_obj.validate(mock_request)
    return mock_request


def create_bearer_token(
    key, secrets_dict, sub=None, channel=None, utc_now=None, expire_in=30, prefix="bearer", algorithm="HS512"
):
    secret = secrets_dict[key]
    if utc_now is None:
        iat = datetime.datetime.utcnow()
    else:
        iat = utc_now
    exp = iat + datetime.timedelta(seconds=expire_in)
    payload = {"exp": exp, "iat": iat}
    if channel is not None:
        payload["channel"] = channel
    if sub is not None:
        payload["sub"] = str(sub)
    token = jwt.encode(payload, secret, headers={"kid": key}, algorithm=algorithm)
    return f"{prefix} {token}"


class TestAuth:
    @classmethod
    def setup_class(cls):
        cls.secrets_dict = {"test_key-1": "my_secret_1"}
        cls.sub = 39624
        cls.channel = "com_bink.wallet"

    def test_auth_valid(self):
        with patch.dict("app.api.auth.vault_access_secret", self.secrets_dict):
            auth_token = create_bearer_token("test_key-1", self.secrets_dict, self.sub, self.channel)
            mock_request = validate_mock_request(auth_token)
            assert get_authenticated_user(mock_request) == self.sub
            assert get_authenticated_channel(mock_request) == self.channel

    def test_auth_invalid_key(self):
        with patch.dict("app.api.auth.vault_access_secret", {"test_key-2": "my_secret_1"}):
            try:
                auth_token = create_bearer_token("test_key-1", self.secrets_dict, self.sub, self.channel)
                validate_mock_request(auth_token)
                assert False, "Did not detect invalid key"
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token has unknown secret"
                assert e.code == "INVALID_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_auth_invalid_secret(self):
        with patch.dict("app.api.auth.vault_access_secret", {"test_key-1": "my_secret_bad"}):
            try:
                auth_token = create_bearer_token("test_key-1", self.secrets_dict, self.sub, self.channel)
                validate_mock_request(auth_token)
                assert False, "Did not detect invalid key"
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token signature error: Signature verification failed"
                assert e.code == "INVALID_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_auth_time_out(self):
        with patch.dict("app.api.auth.vault_access_secret", {"test_key-1": "my_secret_1"}):
            try:
                auth_token = create_bearer_token(
                    "test_key-1",
                    self.secrets_dict,
                    self.sub,
                    self.channel,
                    utc_now=datetime.datetime.utcnow() - datetime.timedelta(seconds=500),
                )
                validate_mock_request(auth_token)
                assert False, "Did not detect time out"
            except falcon.HTTPUnauthorized as e:
                assert e.title == "Access Token expired: Signature has expired"
                assert e.code == "EXPIRED_TOKEN"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_missing_sub_claim(self):
        with patch.dict("app.api.auth.vault_access_secret", {"test_key-1": "my_secret_1"}):
            try:
                auth_token = create_bearer_token("test_key-1", self.secrets_dict, channel=self.channel)
                mock_request = validate_mock_request(auth_token)
                assert get_authenticated_user(mock_request) == self.sub
                assert get_authenticated_channel(mock_request) == self.channel
                assert False, "Did not detect missing sub claim"
            except falcon.HTTPUnauthorized as e:
                assert e.title == 'Token has Missing claim "sub" in Access Token'
                assert e.code == "MISSING CLAIM"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

    def test_missing_channel_claim(self):
        with patch.dict("app.api.auth.vault_access_secret", {"test_key-1": "my_secret_1"}):
            try:
                auth_token = create_bearer_token("test_key-1", self.secrets_dict, sub=self.sub)
                mock_request = validate_mock_request(auth_token)
                assert get_authenticated_user(mock_request) == self.sub
                assert get_authenticated_channel(mock_request) == self.channel
                assert False, "Did not detect missing channel claim"
            except falcon.HTTPUnauthorized as e:
                assert e.title == 'Token has Missing claim "channel" in Access Token'
                assert e.code == "MISSING CLAIM"
                assert e.status == falcon.HTTP_401
            except Exception as e:
                assert False, f"Exception in code or test {e}"

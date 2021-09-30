import datetime
from unittest.mock import Mock

import falcon
import jwt


class MockContext:
    auth_obj = None
    auth_instance = auth_obj


def setup_mock_request(auth_header, auth_class, media=None):
    """
    Makes a mock request object which holds the relevant data just like falcon.request
    Sets the mock context up in same way as middleware does setting
    context.auth_instance to an instance of AccessToken

    :param media:
    :param auth_class:
    :param auth_header:
    :return: mock_request
    """
    mock_request = Mock(spec=falcon.Request)
    mock_request.context = MockContext
    mock_request.context.auth_obj = auth_class
    mock_request.context.auth_instance = auth_class()
    mock_request.auth = auth_header
    if media is not None:
        mock_request.media = media
    return mock_request


def validate_mock_request(auth_token, auth_class, media=None):
    """
    Sets up request object and with authentication object as middleware

    :param media:
    :param auth_class:
    :param auth_token:
    :return: mock_request
    """
    mock_request = setup_mock_request(auth_token, auth_class, media)
    auth_obj = mock_request.context.auth_instance
    auth_obj.validate(mock_request)
    return mock_request


def create_access_token(
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


def create_b2b_token(
    key, sub=None, kid=None, email=None, utc_now=None, expire_in=30, prefix="bearer", algorithm="RS512"
):
    if utc_now is None:
        iat = datetime.datetime.utcnow()
    else:
        iat = utc_now
    exp = iat + datetime.timedelta(seconds=expire_in)
    payload = {"exp": exp, "iat": iat}
    if email is not None:
        payload["email"] = email
    if sub is not None:
        payload["sub"] = sub
    token = jwt.encode(payload, key, headers={"kid": kid}, algorithm=algorithm)
    return f"{prefix} {token}"


def create_refresh_token(
    key, secrets_dict, kid=None, payload=None, utc_now=None, expire_in=30, prefix="bearer", algorithm="HS512"
):
    secret = secrets_dict[key]
    if utc_now is None:
        iat = datetime.datetime.utcnow()
    else:
        iat = utc_now
    exp = iat + datetime.timedelta(seconds=expire_in)
    if payload is None:
        payload = {}
    payload["exp"] = exp
    payload["iat"] = iat
    token = jwt.encode(payload, secret, headers={"kid": kid}, algorithm=algorithm)
    return f"{prefix} {token}"

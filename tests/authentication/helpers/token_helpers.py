import datetime
from unittest.mock import Mock

import falcon
import jwt

from app.api.auth import BaseAuth


class MockContext:
    auth_obj: type[BaseAuth] | None = None
    auth_instance: BaseAuth | None = None


def setup_mock_request(auth_header: dict | str, auth_class: type[BaseAuth], media: dict | None = None) -> Mock:
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


def validate_mock_request(auth_token: str, auth_class: type[BaseAuth], media: dict | None = None) -> Mock:
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
    key: str,
    secrets_dict: dict,
    sub: int | None = None,
    channel: str | None = None,
    is_tester: bool | None = None,
    is_trusted_channel: bool | None = None,
    utc_now: datetime.datetime | None = None,
    expire_in: int = 30,
    prefix: str = "bearer",
    algorithm: str = "HS512",
) -> str:
    secret = secrets_dict[key]
    iat = datetime.datetime.now(tz=datetime.UTC) if utc_now is None else utc_now
    exp = iat + datetime.timedelta(seconds=expire_in)
    payload: dict = {"exp": exp, "iat": iat}
    if channel is not None:
        payload["channel"] = channel
    if sub is not None:
        payload["sub"] = str(sub)
    if is_tester is not None:
        payload["is_tester"] = is_tester
    if is_trusted_channel is not None:
        payload["is_trusted_channel"] = is_trusted_channel

    token = jwt.encode(payload, secret, headers={"kid": key}, algorithm=algorithm)
    return f"{prefix} {token}"


def create_b2b_token(
    key: str,
    sub: str | None = None,
    kid: str | None = None,
    email: str | None = None,
    utc_now: datetime.datetime | None = None,
    expire_in: int = 30,
    prefix: str = "bearer",
    algorithm: str = "RS512",
    allow_none: bool = False,
    expired: bool = False,
) -> str:
    iat = utc_now or datetime.datetime.now(tz=datetime.UTC)
    delta = datetime.timedelta(seconds=expire_in)
    exp = iat - delta if expired else iat + delta
    payload: dict = {"exp": exp, "iat": iat}
    if email is not None or allow_none:
        payload["email"] = email
    if sub is not None:
        payload["sub"] = sub
    token = jwt.encode(payload, key, headers={"kid": kid}, algorithm=algorithm)
    return f"{prefix} {token}"


def create_refresh_token(
    key: str,
    secrets_dict: dict,
    kid: str | None = None,
    payload: dict | None = None,
    utc_now: datetime.datetime | None = None,
    expire_in: int = 30,
    prefix: str = "bearer",
    algorithm: str = "HS512",
    expired: bool = False,
) -> str:
    secret = secrets_dict[key]
    iat = datetime.datetime.now(tz=datetime.UTC) if utc_now is None else utc_now
    delta = datetime.timedelta(seconds=expire_in)
    exp = iat - delta if expired else iat + delta
    if payload is None:
        payload = {}
    payload["exp"] = exp
    payload["iat"] = iat
    token = jwt.encode(payload, secret, headers={"kid": kid}, algorithm=algorithm)
    return f"{prefix} {token}"

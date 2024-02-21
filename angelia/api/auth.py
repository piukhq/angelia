import datetime
from abc import ABC, abstractmethod
from base64 import b64decode
from collections.abc import Callable
from functools import lru_cache, wraps
from typing import Any, cast

import falcon
import jwt
from shared_config_storage.vault.secrets import VaultError
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from voluptuous import MultipleInvalid

from angelia.api.custom_error_handlers import (
    INVALID_CLIENT,
    INVALID_GRANT,
    INVALID_REQUEST,
    UNAUTHORISED_CLIENT,
    UNSUPPORTED_GRANT_TYPE,
    TokenHTTPError,
)
from angelia.api.helpers.vault import dynamic_get_b2b_token_secret, get_access_token_secret
from angelia.api.validators import check_valid_email
from angelia.hermes.db import DB
from angelia.hermes.models import Channel, ClientApplication
from angelia.report import ctx


class BaseAuth(ABC):
    @abstractmethod
    def validate(self, request: falcon.Request) -> dict:
        ...


def get_authenticated_user(req: falcon.Request) -> int:
    user_id = int(BaseJwtAuth.get_claim_from_request(req, "sub"))
    ctx.user_id = user_id
    return user_id


def get_authenticated_token_user(req: falcon.Request) -> int:
    user_id = int(BaseJwtAuth.get_claim_from_token_request(req, "sub"))
    ctx.user_id = user_id
    return user_id


def get_authenticated_token_client(req: falcon.Request) -> str:
    return BaseJwtAuth.get_claim_from_token_request(req, "client_id")


def get_authenticated_external_user(req: falcon.Request) -> str:
    return BaseJwtAuth.get_claim_from_token_request(req, "sub")


def get_authenticated_external_user_email(req: falcon.Request, email_required: bool = True) -> str:
    try:
        email = BaseJwtAuth.get_claim_from_token_request(req, "email")
    except TokenHTTPError:
        # No email claim found in the token
        if not email_required:
            return ""
        raise

    # Checks for these specifically so a false bool value is not accepted
    if not email_required and email in (None, ""):
        return ""

    try:
        check_valid_email({"email": str(email).lower()})  # noqa: FURB123, RUF100
        # Checks validity of the email through email validator
    except MultipleInvalid:
        raise TokenHTTPError(INVALID_GRANT) from None

    return email


def get_authenticated_external_channel(req: falcon.Request) -> str:
    return BaseJwtAuth.get_claim_from_token_request(req, "channel")


def get_authenticated_channel(req: falcon.Request) -> str:
    return BaseJwtAuth.get_claim_from_request(req, "channel")


def get_authenticated_tester_status(req: falcon.Request) -> bool:
    return cast(bool, BaseJwtAuth.get_claim_from_request(req, "is_tester"))


def get_authenticated_trusted_channel_status(req: falcon.Request) -> str:
    return BaseJwtAuth.get_claim_from_request(req, "is_trusted_channel")


def trusted_channel_only(func: "Callable[..., Any]") -> "Callable[..., None]":
    """
    Decorator function to validate if the calling user is of a trusted channel and
    raises HTTPForbidden if not.

    This should be executed before input validation.
    """

    @wraps(func)
    def decorator(*args: Any, **kwargs: Any) -> None:
        req = None
        for arg in args:
            if isinstance(arg, falcon.Request):
                req = arg
                break

        if not req:
            raise ValueError("Decorated function must contain falcon.Request argument")

        is_trusted = get_authenticated_trusted_channel_status(req)

        if is_trusted:
            func(*args, **kwargs)
        else:
            raise falcon.HTTPForbidden

    return decorator


class NoAuth(BaseAuth):
    def validate(self, reg: falcon.Request) -> dict:  # noqa: ARG002
        return {}


class BaseJwtAuth(BaseAuth):
    def __init__(self, type_name: str, token_prefix: str) -> None:
        self.token_type = type_name
        self.token_prefix = token_prefix
        self.jwt_payload: str = None  # type: ignore [assignment]
        self.headers: dict = None  # type: ignore [assignment]
        self.auth_data: dict = None  # type: ignore [assignment]

    def validate(self, request: falcon.Request) -> dict:  # noqa: ARG002
        raise falcon.HTTPInternalServerError(title="BaseJwtAuth must be overridden")

    @classmethod
    def get_claim_from_request(cls, req: falcon.Request, key: str | None = None) -> str:
        try:
            auth = req.context.auth_instance
        except AttributeError:
            raise falcon.HTTPUnauthorized(
                title="Request context does not have an auth instance", code="INVALID_TOKEN"
            ) from None
        return auth.get_claim(key)

    @classmethod
    def get_claim_from_token_request(cls, req: falcon.Request, key: str | None = None) -> str:
        try:
            auth = req.context.auth_instance
        except AttributeError:
            raise TokenHTTPError(INVALID_GRANT) from None
        return auth.get_token_claim(key)

    def get_claim(self, key: str) -> str:
        if key not in self.auth_data:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} has missing claim", code="MISSING_CLAIM")
        return self.auth_data[key]

    def get_token_claim(self, key: str) -> str:
        if key not in self.auth_data:
            raise TokenHTTPError(INVALID_GRANT)
        return self.auth_data[key]

    def _load_auth_token_data(self, request: falcon.Request) -> tuple[str, str]:
        auth = request.auth
        if not auth:
            raise falcon.HTTPUnauthorized(title="No Authentication Header")

        parsed_auth = auth.split()
        if len(parsed_auth) != 2:
            raise falcon.HTTPUnauthorized(
                title=f"{self.token_type} must be in 2 parts separated by a space", code="INVALID_TOKEN"
            )

        return parsed_auth[0].lower(), parsed_auth[1]

    def get_token_from_header(self, request: falcon.Request) -> None:
        prefix, self.jwt_payload = self._load_auth_token_data(request)

        if prefix != self.token_prefix:
            raise falcon.HTTPUnauthorized(
                title=f"{self.token_type} must have {self.token_prefix} prefix", code="INVALID_TOKEN"
            )
        try:
            self.headers = jwt.get_unverified_header(self.jwt_payload)
        except (jwt.DecodeError, jwt.InvalidTokenError):
            raise falcon.HTTPUnauthorized(title="Supplied token is invalid", code="INVALID_TOKEN") from None

    def decode_jwt_token(
        self,
        secret: str,
        options: dict | None = None,
        algorithms: list[str] | None = None,
        leeway_secs: int = 0,
    ) -> None:
        if options is None:
            options = {}
        if algorithms is None:
            algorithms = ["HS512"]

        self.auth_data = jwt.decode(
            self.jwt_payload,
            secret,
            leeway=datetime.timedelta(seconds=leeway_secs),
            algorithms=algorithms,
            options=options,
        )

    def validate_jwt_access_token(
        self,
        secret: str | None = None,
        options: dict | None = None,
        algorithms: list[str] | None = None,
        leeway_secs: int = 0,
    ) -> None:
        if not secret:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} has unknown secret", code="INVALID_TOKEN")
        try:
            self.decode_jwt_token(secret, options, algorithms, leeway_secs)
            if any(key not in self.auth_data for key in ("sub", "iat", "exp")):
                raise falcon.HTTPUnauthorized(title=f"{self.token_type} has missing claim", code="MISSING_CLAIM")

        except jwt.InvalidSignatureError as e:
            raise falcon.HTTPUnauthorized(
                title=f"{self.token_type} signature error: {e}", code="INVALID_TOKEN"
            ) from None
        except jwt.ExpiredSignatureError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} expired: {e}", code="EXPIRED_TOKEN") from None
        except jwt.DecodeError as e:
            raise falcon.HTTPUnauthorized(
                title=f"{self.token_type} encoding Error: {e}", code="INVALID_TOKEN"
            ) from None
        except jwt.InvalidTokenError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} is invalid: {e}", code="INVALID_TOKEN") from None

    def validate_jwt_token(
        self,
        secret: str | None = None,
        options: dict | None = None,
        algorithms: list[str] | None = None,
        leeway_secs: int = 0,
    ) -> None:
        if not secret:
            raise TokenHTTPError(UNAUTHORISED_CLIENT)
        try:
            self.decode_jwt_token(secret, options, algorithms, leeway_secs)
            if any(key not in self.auth_data for key in ("sub", "iat", "exp")):
                raise TokenHTTPError(INVALID_GRANT)
        except jwt.InvalidSignatureError:
            raise TokenHTTPError(UNAUTHORISED_CLIENT) from None
        except jwt.ExpiredSignatureError:
            raise TokenHTTPError(INVALID_GRANT) from None
        except (jwt.DecodeError, jwt.InvalidTokenError, Exception):
            raise TokenHTTPError(INVALID_REQUEST) from None


class AccessToken(BaseJwtAuth):
    def __init__(self) -> None:
        super().__init__("Access Token", "bearer")

    def validate(self, request: falcon.Request) -> dict:
        """
        This is the Access Token which is signed using an rotating secret key stored in vault.

        All the claims are signed so if removed will cause an authentication error.

        There is no need to check for the presence of the claims in the token - this can be trusted as the token
        end point generates and signs the token.

        Claims should not be accessed directly but obtained via get functions such as "get_authenticated_user"
        for code consistency the function will raise an authentication error if the claim is absent.

        """
        self.get_token_from_header(request)

        if "kid" not in self.headers:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} must have a kid header", code="INVALID_TOKEN")
        secret = get_access_token_secret(self.headers["kid"])
        # Note a secret = False raises an error
        self.validate_jwt_access_token(secret=secret, algorithms=["HS512"], leeway_secs=5)
        return self.auth_data


class ClientSecretAuthMixin:
    @staticmethod
    @lru_cache
    def validate_client_secret(bundle_id: str, client_secret: str) -> bool:
        return (
            cast(Session, DB().session).scalar(
                select(Channel.bundle_id)
                .join(ClientApplication)
                .where(
                    Channel.bundle_id == bundle_id,
                    ClientApplication.secret == client_secret,
                )
            )
        ) is not None

    def handle_basic_auth(self, token: str) -> None:
        try:
            token_payload = b64decode(token).decode("utf-8")
            username, password = token_payload.split(":", 1)
        except Exception:
            raise falcon.HTTPUnauthorized(title="Supplied token is invalid", code="INVALID_TOKEN") from None

        self.headers = {
            "bundle_id": username,
            "client_secret": password,
        }

    def handle_client_credentials_grant(self, request_media: dict) -> None:
        if not (
            (bundle_id := self.headers.get("bundle_id"))
            and (client_secret := self.headers.get("client_secret"))
            and (username := request_media.pop("username"))
            and self.validate_client_secret(bundle_id, client_secret)
        ):
            raise TokenHTTPError(INVALID_REQUEST)

        self.auth_data = {"channel": bundle_id, "sub": username}


class ClientToken(BaseJwtAuth, ClientSecretAuthMixin):
    media_token_key: str | None = None

    def __init__(self) -> None:
        super().__init__("B2B Client Token or Secret", "bearer")

    def get_token_from_header(self, request: falcon.Request) -> None:
        prefix, token = self._load_auth_token_data(request)

        if prefix == self.token_prefix:
            self.jwt_payload = token
            try:
                self.headers = jwt.get_unverified_header(self.jwt_payload)
            except (jwt.DecodeError, jwt.InvalidTokenError):
                raise falcon.HTTPUnauthorized(title="Supplied token is invalid", code="INVALID_TOKEN") from None

        elif prefix == "basic":
            self.handle_basic_auth(token)

        else:
            raise falcon.HTTPUnauthorized(
                title=f"{self.token_type} must have '{self.token_prefix}' or 'basic' prefix", code="INVALID_TOKEN"
            )

    def check_request(self, request: falcon.Request, request_media: dict) -> str:
        self.get_token_from_header(request)
        try:
            grant_type = request_media.get("grant_type")
            scope_list = request_media.get("scope")
        except falcon.MediaMalformedError:
            raise TokenHTTPError(INVALID_REQUEST) from None

        if grant_type == "client_credentials":
            required_len = 3
        else:
            required_len = 2
            if "kid" not in self.headers:
                raise TokenHTTPError(INVALID_REQUEST)

        if len(request_media) != required_len:
            raise TokenHTTPError(INVALID_REQUEST)
        if scope_list is None or len(scope_list) != 1:
            raise TokenHTTPError(INVALID_REQUEST)
        scope = scope_list.pop()
        if grant_type is None or scope != "user":
            raise TokenHTTPError(INVALID_REQUEST)
        return grant_type

    def validate(self, request: falcon.Request) -> dict:
        """
        This is the OAuth2 style access token which has to validate that the user exists and is using the correct
        channel.  The kid defines the key used to sign the token.  This kid is issued to the B2B client for their use
        only and with it we store the channel name and public signing key.

        A client cannot pretend to be another channel because they would not be able to successfully sign the token
        without the correct private key. The associated public key has a fixed relationship to the kid and channel so
        cannot be forged.

        No need to check contents of token as they are signed and we use get functions to check that expected claim is
        present and valid.  This makes it easier to extend the claim.
        """
        request_media = request.media.get(self.media_token_key, request.media)
        match self.check_request(request, request_media):
            case "b2b":
                try:
                    all_b2b_secrets = dynamic_get_b2b_token_secret(self.headers["kid"])
                except VaultError as e:
                    raise TokenHTTPError(INVALID_CLIENT) from e
                if not all_b2b_secrets:
                    raise TokenHTTPError(UNAUTHORISED_CLIENT)
                public_key = all_b2b_secrets["key"]
                self.validate_jwt_token(secret=public_key, algorithms=["RS512", "EdDSA"], leeway_secs=5)
                self.auth_data["channel"] = all_b2b_secrets["channel"]

            case "refresh_token":
                pre_fix_kid, post_fix_kid = self.headers["kid"].split("-", 1)
                if pre_fix_kid != "refresh":
                    raise TokenHTTPError(INVALID_REQUEST)
                secret = get_access_token_secret(post_fix_kid)
                self.validate_jwt_token(secret=secret, algorithms=["HS512"], leeway_secs=5)

            case "client_credentials":
                self.handle_client_credentials_grant(request_media)

            case _:
                raise TokenHTTPError(UNSUPPORTED_GRANT_TYPE)

        return self.auth_data


class WalletClientToken(ClientToken):
    media_token_key = "token"

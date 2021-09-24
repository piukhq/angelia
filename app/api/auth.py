import datetime

import falcon
import jwt

from app.api.helpers.vault import get_access_token_secret, dynamic_get_b2b_token_secret
from app.report import ctx
from app.api.custom_error_handlers import TokenHTTPError


def get_authenticated_user(req: falcon.Request):
    user_id = int(BaseJwtAuth.get_claim_from_request(req, "sub"))
    ctx.user_id = user_id
    return user_id


def get_authenticated_external_user(req: falcon.Request):
    external_id = BaseJwtAuth.get_claim_from_request(req, "sub")
    return external_id


def get_authenticated_user_email(req: falcon.Request):
    email = BaseJwtAuth.get_claim_from_request(req, "email")
    return email


def get_authenticated_channel(req: falcon.Request):
    return BaseJwtAuth.get_claim_from_request(req, "channel")


class NoAuth:
    def validate(self, reg: falcon.Request):
        return {}


class BaseJwtAuth:
    def __init__(self, type_name, token_prefix):
        self.token_type = type_name
        self.token_prefix = token_prefix
        self.jwt_payload = None
        self.headers = None
        self.auth_data = None

    def validate(self, request: falcon.Request):
        raise falcon.HTTPInternalServerError(title="BaseJwtAuth must be overridden")

    @classmethod
    def get_claim_from_request(cls, req: falcon.Request, key=None):
        try:
            auth = getattr(req.context, "auth_instance")
        except AttributeError:
            raise falcon.HTTPInternalServerError(title="Request context does not have an auth instance")
        return auth.get_claim(key)

    def get_claim(self, key):
        if key not in self.auth_data:
            raise falcon.HTTPUnauthorized(
                title=f'Token has Missing claim "{key}" in {self.token_type}', code="MISSING CLAIM"
            )
        return self.auth_data[key]

    def get_token_from_header(self, request: falcon.Request):
        auth = request.auth
        if not auth:
            raise falcon.HTTPUnauthorized(title="No Authentication Header")
        auth = auth.split()
        if len(auth) != 2:
            raise falcon.HTTPUnauthorized(
                title=f"{self.token_type} must be in 2 parts separated by a space", code="INVALID_TOKEN"
            )

        prefix = auth[0].lower()
        self.jwt_payload = auth[1]
        if prefix != self.token_prefix:
            raise falcon.HTTPUnauthorized(
                title=f"{self.token_type} must have {self.token_prefix} prefix", code="INVALID_TOKEN"
            )
        try:
            self.headers = jwt.get_unverified_header(self.jwt_payload)
        except (jwt.DecodeError, jwt.InvalidTokenError):
            raise falcon.HTTPUnauthorized(title="Supplied token is invalid", code="INVALID_TOKEN")

    def validate_jwt_access_token(self, secret=None, options=None, algorithms=None, leeway_secs=0):
        if options is None:
            options = {}
        if algorithms is None:
            algorithms = ["HS512"]

        if not secret:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} has unknown secret", code="INVALID_TOKEN")
        try:
            self.auth_data = jwt.decode(
                self.jwt_payload,
                secret,
                leeway=datetime.timedelta(seconds=leeway_secs),
                algorithms=algorithms,
                options=options,
            )

        except jwt.InvalidSignatureError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} signature error: {e}", code="INVALID_TOKEN")
        except jwt.ExpiredSignatureError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} expired: {e}", code="EXPIRED_TOKEN")
        except jwt.DecodeError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} encoding Error: {e}", code="INVALID_TOKEN")
        except jwt.InvalidTokenError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} is invalid: {e}", code="INVALID_TOKEN")


class AccessToken(BaseJwtAuth):
    def __init__(self):
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


class ClientToken(BaseJwtAuth):
    def __init__(self):
        super().__init__("B2B Client Token", "bearer")

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
        self.get_token_from_header(request)
        grant_type = request.media.get("grant_type")
        if "kid" not in self.headers:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} must have a kid header", code="INVALID_TOKEN")

        if grant_type == 'b2b':
            secret_record = dynamic_get_b2b_token_secret(self.headers["kid"])
            if not secret_record:
                raise falcon.HTTPUnauthorized(title=f"{self.token_type} has unknown secret", code="INVALID_TOKEN")
            public_key = secret_record['key']
            self.validate_jwt_access_token(secret=public_key, algorithms=["RS512"])
            self.auth_data['channel'] = secret_record['channel']
            return self.auth_data
        elif grant_type == 'refresh_token':
            secret = get_access_token_secret(self.headers["kid"])
            self.validate_jwt_access_token(secret=secret, algorithms=["HS512"], leeway_secs=5)
            return self.auth_data
        else:
            raise TokenHTTPError("400", "invalid_grant")

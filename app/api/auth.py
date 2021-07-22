import datetime

import falcon
import jwt

from settings import vault_access_secret


def get_authenticated_user(req: falcon.Request):
    return BaseJwtAuth.get_claim_from_request(req, "sub")


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
            raise falcon.HTTPUnauthorized(title=f"Missing claim {key} in {self.token_type}")
        return self.auth_data[key]

    def get_token_from_header(self, request: falcon.Request):
        auth = request.auth
        if not auth:
            raise falcon.HTTPUnauthorized(title="No Authentication Header")
        auth = auth.split()
        if len(auth) != 2:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} must be in 2 parts separated by a space")

        prefix = auth[0].lower()
        self.jwt_payload = auth[1]
        if prefix != self.token_prefix:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} must have {self.token_type} prefix")
        self.headers = jwt.get_unverified_header(self.jwt_payload)

    def validate_jwt_token(self, secret=None, options=None, algorithms=None, leeway_secs=0):
        if options is None:
            options = {}
        if algorithms is None:
            algorithms = ["HS512"]

        if not secret:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} has unknown secret")
        try:
            self.auth_data = jwt.decode(
                self.jwt_payload,
                secret,
                leeway=datetime.timedelta(seconds=leeway_secs),
                algorithms=algorithms,
                options=options,
            )

        except jwt.InvalidSignatureError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} signature error: {e}")
        except jwt.ExpiredSignatureError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} expired: {e}")
        except jwt.DecodeError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} encoding Error: {e}")
        except jwt.InvalidTokenError as e:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} is invalid: {e}")


class AccessToken(BaseJwtAuth):
    def __init__(self):
        super().__init__("Access Token", "bearer")

    def validate(self, request: falcon.Request):
        """
        This is the OAuth2 style access token which for mvp  purposes is not signed but will be when the Authentication
        end point is created.

        No need to check contents of token as they are validated by gets so only fails if essential info is missing
        hence access to resource is granted if class defined in resource validate
        """
        self.get_token_from_header(request)

        if "kid" not in self.headers:
            raise falcon.HTTPUnauthorized(title=f"{self.token_type} must have a kid header")
        secret = vault_access_secret.get(self.headers["kid"])

        self.validate_jwt_token(secret)

        return self.auth_data

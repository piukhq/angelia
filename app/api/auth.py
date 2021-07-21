import datetime

import falcon
import jwt

from app.api.exceptions import AuthenticationError
from settings import vault_access_secret


def get_authenticated_user(req: falcon.Request):
    params = getattr(req.context, "authenticated")
    user_id = params.get("user_id", None)
    if not user_id:
        raise AuthenticationError()
    return user_id


def get_authenticated_channel(req: falcon.Request):
    params = getattr(req.context, "authenticated")
    channel_id = params.get("channel", None)
    if not channel_id:
        raise AuthenticationError()
    return channel_id


class NoAuth:
    def validate(self, reg: falcon.Request):
        return {}


class AccessToken:
    def validate(self, request: falcon.Request):
        """
        This is the OAuth2 style access token which for mvp  purposes is not signed but will be when the Authentication
        end point is created.

        No need to check contents of token as they are validated by gets so only fails if essential info is missing
        hence access to resource is granted if class defined in resource validate
        """
        auth = request.auth
        if not auth:
            raise AuthenticationError(title="No Authentication Header")
        auth = auth.split()
        if len(auth) != 2:
            raise AuthenticationError(title="Token must be in 2 parts separated by a space")

        prefix = auth[0].lower()
        jwt_payload = auth[1]

        if prefix != "bearer":
            raise AuthenticationError(title="Auth token must have Bearer prefix")
        headers = jwt.get_unverified_header(jwt_payload)

        if "kid" not in headers:
            raise AuthenticationError(title="Auth token must have a kid header")
        secret = vault_access_secret.get(headers["kid"])
        if not secret:
            raise AuthenticationError(title="Auth token has unknown secret")
        try:
            auth_data = jwt.decode(
                jwt_payload,
                secret,
                leeway=datetime.timedelta(seconds=10),
                algorithms=["HS512"],
                # options={"verify_signature": False}   # remove this option when validating secrets
            )

        except jwt.InvalidSignatureError as e:
            raise AuthenticationError(title=f"Access token signature error: {e}")
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationError(title=f"Access token expired: {e}")
        except jwt.DecodeError as e:
            raise AuthenticationError(title=f"Access token encoding Error: {e}")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(title=f"Access token is invalid: {e}")

        return auth_data

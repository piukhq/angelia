from collections import namedtuple

import falcon
import requests
from jose import jwt

import settings
from app.api.exceptions import AuthenticationError
from app.report import api_logger


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


class BinkJWTs:

    def validate(self, reg: falcon.Request):
        """
        @todo add jwt validate for Token or Bearer  ie Bink or Barclays respectively
        This is a bad use of tokens because there is no regular key rotation. In case of Barclays there is only one
        shared secret. Also it is difficult to trust a token which is not recently generated eg the user may have been
        deleted. see proposal below

        In Barclays case this secret is obtained from the vault on start up so no BD lookup is required to validate.
        In Bink app case the secret requires a salt stored in the user table so some look up or caching is required
        or we will add at least 10ms to the response.  This lookup is often inefficient because the user is often
        combined in a lookup for the API


        No need to check contents of token as they are validated by gets so only fails if essential info is missing

        hence access to resource is granted if class defined in resource validate
        """

        return {"user_id": 457, "channel": "com.bink.web"}


class Auth2JWTs:

    def validate(self, reg: falcon.Request):
        """
         @todo consider a better token
         We need and endpoint to exchange tokens using a rotated secret; the jwt contains the id of the
         secret used so that secrets can overlap.
         The database/redis stores the secrets made at random and deleted x hrs after expiry of last used token

         """
        # get_rotated_secret(token)
        # just verify token and return contents - no database look ups
        return {"user_id": 457, "channel": "com.bink.web"}


    def get_tmp_token(self, reg: falcon.Request):
        """
        Get the token and check as for BinkJWT including database lookups.
        This Needs to be done when app starts a session or if using temp token fails with unauthorised then
        a request with perm token is made.  This token should have credentials to prove the user and ideally
        salted per user.

        :return:
        """
        tmp_token = None  # here we sign a token with latest secret
        return tmp_token

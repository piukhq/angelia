import falcon

from app.api.auth import ClientToken, get_authenticated_external_channel, get_authenticated_external_user
from app.api.helpers.vault import get_current_token_secret
from app.api.serializers import TokenSerializer
from app.api.validators import token_schema, validate
from app.handlers.token import TokenGen
from app.report import log_request_data

from .base_resource import Base


class Token(Base):

    auth_class = ClientToken

    @log_request_data
    @validate(req_schema=token_schema, resp_schema=TokenSerializer)
    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        channel = get_authenticated_external_channel(req)
        external_user_id = get_authenticated_external_user(req)
        kid, secret = get_current_token_secret()
        handler = TokenGen(
            db_session=self.session,
            external_user_id=external_user_id,
            channel_id=channel,
            access_kid=kid,
            access_secret_key=secret,
            **req.media
        )
        handler.process_token(req)
        access_token = handler.create_access_token()
        refresh_token = handler.create_refresh_token()
        resp.media = {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": handler.access_life_time,
            "refresh_token": refresh_token,
            "scope": ["user"],
        }
        resp.status = falcon.HTTP_200

        # adds an async task to hermes
        handler.refresh_balances()

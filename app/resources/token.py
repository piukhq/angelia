import falcon
from app.api.auth import (ClientToken, get_authenticated_external_user, get_authenticated_external_channel,
                          get_authenticated_external_user_email)
from app.report import log_request_data
from .base_resource import Base
from app.api.validators import (
    token_schema,
    validate,
)
from app.api.serializers import TokenSerializer
from app.handlers.token import TokenGen
from app.api.helpers.vault import get_current_token_secret


class Token(Base):

    auth_class = ClientToken

    @log_request_data
    @validate(req_schema=token_schema, resp_schema=TokenSerializer)
    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        channel = get_authenticated_external_channel(req)
        external_user_id = get_authenticated_external_user(req)
        email = get_authenticated_external_user_email(req)
        kid, secret = get_current_token_secret()
        handler = TokenGen(db_session=self.session,
                           user_id=0,
                           email=email,
                           external_user_id=external_user_id,
                           channel_id=channel,
                           access_life_time=600,
                           refresh_life_time=900,
                           access_kid=kid,
                           access_secret_key=secret,
                           **req.media)
        handler.verify_client_token()
        access_token = handler.create_access_token()
        refresh_token = handler.create_refresh_token()
        print(access_token, refresh_token)
        resp.media = {}
        resp.status = falcon.HTTP_201


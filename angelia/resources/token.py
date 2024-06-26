from typing import Any

import falcon

from angelia.api.auth import ClientToken, get_authenticated_external_channel, get_authenticated_external_user
from angelia.api.helpers.vault import get_current_token_secret
from angelia.api.metrics import Metric
from angelia.api.serializers import TokenSerializer
from angelia.api.validators import token_schema, validate
from angelia.handlers.token import TokenGen
from angelia.report import log_request_data
from angelia.resources.base_resource import Base


class Token(Base):
    auth_class = ClientToken

    @log_request_data
    @validate(req_schema=token_schema, resp_schema=TokenSerializer)
    def on_post(self, req: falcon.Request, resp: falcon.Response, *args: Any) -> None:  # noqa: ARG002
        channel = get_authenticated_external_channel(req)
        external_user_id = get_authenticated_external_user(req)
        kid, secret = get_current_token_secret()
        handler = TokenGen(
            db_session=self.session,
            external_user_id=external_user_id,
            channel_id=channel,
            access_kid=kid,
            access_secret_key=secret,
            **req.context.validated_media,
        )
        handler.process_token(req)
        access_token = handler.create_access_token()
        refresh_token = handler.create_refresh_token()

        # adds an async task to hermes
        handler.refresh_balances()

        resp.media = {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": handler.access_life_time,
            "refresh_token": refresh_token,
            "scope": ["user"],
        }

        resp.status = falcon.HTTP_200

        metric = Metric(request=req, status=falcon.HTTP_200)
        metric.route_metric()

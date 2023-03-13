import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.metrics import Metric
from app.api.serializers import EmailUpdateSerializer
from app.api.validators import email_update_schema, empty_schema, validate
from app.handlers.user import UserHandler
from app.report import log_request_data

from .base_resource import Base


class User(Base):
    def get_handler(self, req: falcon.Request) -> UserHandler:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        media = req.context.validated_media or {}

        handler = UserHandler(
            db_session=self.session,
            user_id=user_id,
            channel_id=channel,
            new_email=media.get("email").lower() if media else ""
        )
        return handler

    @log_request_data
    @validate(req_schema=email_update_schema, resp_schema=EmailUpdateSerializer)
    def on_post_email_update(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req)
        handler.handle_email_update()
        resp.media = {"id": handler.user_id}
        resp.status = falcon.HTTP_200
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @validate(req_schema=empty_schema, resp_schema=None)
    def on_delete(self, req: falcon.Request, resp: falcon.Response) -> None:
        # User delete functionality not currently split by token type/origin (i.e. B2B vs B2C) - we may wish to do this
        # in the future when we implement B2C tokens.
        handler = self.get_handler(req)
        handler.send_for_deletion()  # Thin task - we always respond with a 202 as this is a request to delete the
        # user_id in the token. We do not check for the existence of the user as we assume from the token being issued
        # that it exists (within the lifetime of the token).
        resp.status = falcon.HTTP_202
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

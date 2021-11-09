import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.validators import email_update_schema, validate
from app.handlers.user import UserHandler
from app.report import log_request_data

from .base_resource import Base


class User(Base):
    def get_handler(self, req: falcon.Request) -> UserHandler:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        media = req.get_media(default_when_empty={})

        handler = UserHandler(
            db_session=self.session,
            user_id=user_id,
            channel_id=channel,
            new_email=media.get("email", None).lower()
            # Emails always lower-cased for storage
        )
        return handler

    @log_request_data
    @validate(req_schema=email_update_schema)
    def on_post_email_update(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req)
        handler.handle_email_update()
        resp.media = {"id": handler.user_id}
        resp.status = falcon.HTTP_200

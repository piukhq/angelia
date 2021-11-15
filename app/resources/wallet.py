import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.serializers import WalletSerializer
from app.api.validators import empty_schema, validate
from app.handlers.wallet import WalletHandler
from app.report import ctx

from .base_resource import Base


class Wallet(Base):
    @validate(req_schema=empty_schema, resp_schema=WalletSerializer)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        user_id = ctx.user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        handler = WalletHandler(db_session=self.session, user_id=user_id, channel_id=channel)
        resp.media = handler.get_response_dict()
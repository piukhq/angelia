import falcon
from .base_resource import Base
from app.hermes.models import SchemeAccountUserAssociation, SchemeAccount, Scheme, SchemeChannelAssociation, \
    SchemeCredentialQuestion, SchemeAccountCredentialAnswer, Channel
from sqlalchemy import insert
from app.api.auth import get_authenticated_user, get_authenticated_channel
from app.messaging.sender import send_message_to_hermes
from datetime import datetime


class PaymentAccounts(Base):

    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        post_data = req.media


# from datetime import datetime

import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.serializers import LoyaltyCardSerializer
from app.api.validators import (
    loyalty_card_add_and_auth_schema,
    loyalty_card_add_and_register_schema,
    loyalty_card_add_schema,
    loyalty_card_authorise_schema,
    validate,
)
from app.handlers.loyalty_card import ADD, ADD_AND_AUTHORISE, ADD_AND_REGISTER, AUTHORISE, LoyaltyCardHandler
from app.report import log_request_data

from .base_resource import Base

# from sqlalchemy import insert

# from app.hermes.models import (
#     Channel,
#     Scheme,
#     SchemeAccount,
#     SchemeAccountCredentialAnswer,
#     SchemeAccountUserAssociation,
#     SchemeChannelAssociation,
#     SchemeCredentialQuestion,
# )
# from app.messaging.sender import send_message_to_hermes


class LoyaltyCard(Base):
    def get_handler(self, req: falcon.Request, journey: str) -> LoyaltyCardHandler:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        handler = LoyaltyCardHandler(
            db_session=self.session,
            user_id=user_id,
            channel_id=channel,
            journey=journey,
            loyalty_plan_id=req.media.get("loyalty_plan_id", None),
            all_answer_fields=req.media["account"],
        )
        return handler

    @log_request_data
    @validate(req_schema=loyalty_card_add_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD)
        created = handler.handle_add_only_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_201 if created else falcon.HTTP_200

    @log_request_data
    @validate(req_schema=loyalty_card_add_and_auth_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add_and_auth(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD_AND_AUTHORISE)
        created = handler.handle_add_auth_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if created else falcon.HTTP_200

    @log_request_data
    @validate(req_schema=loyalty_card_authorise_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_authorise(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int, *args) -> None:
        handler = self.get_handler(req, AUTHORISE)
        handler.card_id = loyalty_card_id
        update_auth = handler.handle_authorise_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if update_auth else falcon.HTTP_200

    @log_request_data
    @validate(req_schema=loyalty_card_add_and_register_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add_and_register(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD_AND_REGISTER)
        created = handler.handle_add_register_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if created else falcon.HTTP_200

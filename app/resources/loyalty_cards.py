import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.metrics import loyalty_card_counter
from app.api.serializers import LoyaltyCardSerializer
from app.api.validators import (
    empty_schema,
    loyalty_card_add_and_auth_schema,
    loyalty_card_add_and_register_schema,
    loyalty_card_add_schema,
    loyalty_card_authorise_schema,
    loyalty_card_join_schema,
    loyalty_card_register_schema,
    validate,
)
from app.handlers.loyalty_card import (
    ADD,
    ADD_AND_AUTHORISE,
    ADD_AND_REGISTER,
    AUTHORISE,
    DELETE,
    JOIN,
    REGISTER,
    LoyaltyCardHandler,
)
from app.report import log_request_data

from .base_resource import Base


class LoyaltyCard(Base):
    def get_handler(self, req: falcon.Request, journey: str) -> LoyaltyCardHandler:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        media = req.get_media(default_when_empty={})

        handler = LoyaltyCardHandler(
            db_session=self.session,
            user_id=user_id,
            channel_id=channel,
            journey=journey,
            loyalty_plan_id=media.get("loyalty_plan_id", None),
            all_answer_fields=media.get("account", {}),
        )
        return handler

    # @log_request_data
    @validate(req_schema=loyalty_card_add_schema, resp_schema=LoyaltyCardSerializer)
    def on_get_by_id(self, req: falcon.Request, loyalty_card_id: int) -> LoyaltyCardHandler:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        
        handler = LoyaltyCardHandler(
            db_session=self.session,
            user_id=user_id,
            channel_id=channel,
            card_id=loyalty_card_id
        )
        return handler


    @log_request_data
    @validate(req_schema=loyalty_card_add_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD)
        created = handler.handle_add_only_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_201 if created else falcon.HTTP_200
        loyalty_card_counter.labels(endpoint=req.path, channel=handler.channel_id, response_status=resp.status).inc()

    @log_request_data
    @validate(req_schema=loyalty_card_add_and_auth_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add_and_auth(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD_AND_AUTHORISE)
        sent_to_hermes = handler.handle_add_auth_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if sent_to_hermes else falcon.HTTP_200
        loyalty_card_counter.labels(endpoint=req.path, channel=handler.channel_id, response_status=resp.status).inc()

    @log_request_data
    @validate(req_schema=loyalty_card_authorise_schema, resp_schema=LoyaltyCardSerializer)
    def on_put_authorise(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int, *args) -> None:
        handler = self.get_handler(req, AUTHORISE)
        handler.card_id = loyalty_card_id
        sent_to_hermes = handler.handle_authorise_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if sent_to_hermes else falcon.HTTP_200

        loyalty_card_counter.labels(endpoint=req.path, channel=handler.channel_id, response_status=resp.status).inc()

    @log_request_data
    @validate(req_schema=loyalty_card_add_and_register_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add_and_register(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD_AND_REGISTER)
        sent_to_hermes = handler.handle_add_register_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if sent_to_hermes else falcon.HTTP_200

        loyalty_card_counter.labels(endpoint=req.path, channel=handler.channel_id, response_status=resp.status).inc()

    @log_request_data
    @validate(req_schema=loyalty_card_register_schema, resp_schema=LoyaltyCardSerializer)
    def on_put_register(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int, *args) -> None:
        handler = self.get_handler(req, REGISTER)
        handler.card_id = loyalty_card_id
        sent_to_hermes = handler.handle_register_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if sent_to_hermes else falcon.HTTP_200

        loyalty_card_counter.labels(endpoint=req.path, channel=handler.channel_id, response_status=resp.status).inc()

    @log_request_data
    @validate(req_schema=loyalty_card_join_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_join(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, JOIN)
        handler.handle_join_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202

        loyalty_card_counter.labels(endpoint=req.path, channel=handler.channel_id, response_status=resp.status).inc()

    @validate(req_schema=empty_schema)
    def on_delete_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int) -> None:
        handler = self.get_handler(req, DELETE)
        handler.card_id = loyalty_card_id
        handler.handle_delete_card()
        resp.status = falcon.HTTP_202

        loyalty_card_counter.labels(endpoint=req.path, channel=handler.channel_id, response_status=resp.status).inc()

    @validate(req_schema=empty_schema)
    def on_delete_join_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int) -> None:
        handler = self.get_handler(req, DELETE)
        handler.card_id = loyalty_card_id
        handler.handle_delete_join()
        resp.status = falcon.HTTP_200

        loyalty_card_counter.labels(endpoint=req.path, channel=handler.channel_id, response_status=resp.status).inc()

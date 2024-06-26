from typing import TYPE_CHECKING, Any

import falcon

from angelia.api.auth import get_authenticated_channel, get_authenticated_user, trusted_channel_only
from angelia.api.metrics import Metric
from angelia.api.serializers import LoyaltyCardSerializer
from angelia.api.validators import (
    empty_schema,
    loyalty_card_add_and_auth_schema,
    loyalty_card_add_and_register_schema,
    loyalty_card_add_schema,
    loyalty_card_authorise_schema,
    loyalty_card_join_schema,
    loyalty_card_put_trusted_add_schema,
    loyalty_card_register_schema,
    loyalty_card_trusted_add_schema,
    validate,
)
from angelia.encryption import decrypt_payload
from angelia.handlers.loyalty_card import (
    ADD,
    ADD_AND_AUTHORISE,
    ADD_AND_REGISTER,
    AUTHORISE,
    DELETE,
    JOIN,
    REGISTER,
    TRUSTED_ADD,
    LoyaltyCardHandler,
)
from angelia.report import log_request_data
from angelia.resources.base_resource import Base

if TYPE_CHECKING:
    from typing import TypeVar

    ResType = TypeVar("ResType")


class LoyaltyCard(Base):
    def get_user_and_channel(self, req: falcon.Request) -> tuple[int, str]:
        user_id = get_authenticated_user(req)
        channel_slug = get_authenticated_channel(req)
        req.context.events_context["user_and_channel"] = (user_id, channel_slug)
        return user_id, channel_slug

    def get_handler(self, req: falcon.Request, journey: str) -> LoyaltyCardHandler:
        user_id, channel_slug = self.get_user_and_channel(req)
        media = req.context.validated_media or {}

        return LoyaltyCardHandler(
            db_session=self.session,
            user_id=user_id,
            channel_id=channel_slug,
            journey=journey,
            loyalty_plan_id=media.get("loyalty_plan_id", None),
            all_answer_fields=media.get("account", {}),
        )

    @decrypt_payload
    @log_request_data
    @validate(req_schema=loyalty_card_add_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add(self, req: falcon.Request, resp: falcon.Response, *args: Any) -> None:  # noqa: ARG002
        handler = self.get_handler(req, ADD)
        created = handler.handle_add_only_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_201 if created else falcon.HTTP_200
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @trusted_channel_only()
    @validate(req_schema=loyalty_card_trusted_add_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_trusted_add(self, req: falcon.Request, resp: falcon.Response, *args: Any) -> None:  # noqa: ARG002
        handler = self.get_handler(req, TRUSTED_ADD)
        req.context.events_context["handler"] = handler

        created = handler.handle_trusted_add_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_201 if created else falcon.HTTP_200
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @trusted_channel_only()
    @validate(req_schema=loyalty_card_put_trusted_add_schema, resp_schema=LoyaltyCardSerializer)
    def on_put_trusted_add(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        loyalty_card_id: int,
        *args: Any,  # noqa: ARG002
    ) -> None:
        handler = self.get_handler(req, TRUSTED_ADD)
        handler.card_id = loyalty_card_id

        created = handler.handle_trusted_update_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_201 if created else falcon.HTTP_200
        metric = Metric(request=req, status=resp.status, resource_id=loyalty_card_id, resource="loyalty_card_id")
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @validate(req_schema=loyalty_card_add_and_auth_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add_and_auth(self, req: falcon.Request, resp: falcon.Response, *args: Any) -> None:  # noqa: ARG002
        handler = self.get_handler(req, ADD_AND_AUTHORISE)
        handler.handle_add_auth_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @validate(req_schema=loyalty_card_authorise_schema, resp_schema=LoyaltyCardSerializer)
    def on_put_authorise(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        loyalty_card_id: int,
        *args: Any,  # noqa: ARG002
    ) -> None:
        handler = self.get_handler(req, AUTHORISE)
        handler.card_id = loyalty_card_id
        sent_to_hermes = handler.handle_authorise_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if sent_to_hermes else falcon.HTTP_200
        metric = Metric(request=req, status=resp.status, resource_id=loyalty_card_id, resource="loyalty_card_id")
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @validate(req_schema=loyalty_card_add_and_register_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add_and_register(self, req: falcon.Request, resp: falcon.Response, *args: Any) -> None:  # noqa: ARG002
        handler = self.get_handler(req, ADD_AND_REGISTER)
        handler.handle_add_register_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @validate(req_schema=loyalty_card_register_schema, resp_schema=LoyaltyCardSerializer)
    def on_put_register(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        loyalty_card_id: int,
        *args: Any,  # noqa: ARG002
    ) -> None:
        handler = self.get_handler(req, REGISTER)
        handler.card_id = loyalty_card_id
        sent_to_hermes = handler.handle_update_register_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if sent_to_hermes else falcon.HTTP_200
        metric = Metric(request=req, status=resp.status, resource_id=loyalty_card_id, resource="loyalty_card_id")
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @validate(req_schema=loyalty_card_join_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_join(self, req: falcon.Request, resp: falcon.Response, *args: Any) -> None:  # noqa: ARG002
        handler = self.get_handler(req, JOIN)
        handler.handle_join_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @validate(req_schema=loyalty_card_join_schema, resp_schema=LoyaltyCardSerializer)
    def on_put_join_by_id(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        loyalty_card_id: int,
        *args: Any,  # noqa: ARG002
    ) -> None:
        handler = self.get_handler(req, JOIN)
        handler.card_id = loyalty_card_id
        resp.media = {"id": handler.card_id}
        handler.handle_put_join()
        resp.status = falcon.HTTP_202
        metric = Metric(request=req, status=resp.status, resource_id=loyalty_card_id, resource="loyalty_card_id")
        metric.route_metric()

    @validate(req_schema=empty_schema)
    def on_delete_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int) -> None:
        handler = self.get_handler(req, DELETE)
        handler.card_id = loyalty_card_id
        handler.handle_delete_card()
        resp.status = falcon.HTTP_202
        metric = Metric(request=req, status=resp.status, resource_id=loyalty_card_id, resource="loyalty_card_id")
        metric.route_metric()

    @validate(req_schema=empty_schema)
    def on_delete_join_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int) -> None:
        handler = self.get_handler(req, DELETE)
        handler.card_id = loyalty_card_id
        handler.handle_delete_join()
        resp.status = falcon.HTTP_200
        metric = Metric(request=req, status=resp.status, resource_id=loyalty_card_id, resource="loyalty_card_id")
        metric.route_metric()

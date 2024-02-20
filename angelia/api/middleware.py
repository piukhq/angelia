import time
from contextlib import suppress
from enum import Enum
from typing import TYPE_CHECKING, cast

import falcon

from angelia.api.helpers.metrics import (
    get_latency_metric,
    get_metrics_as_bytes,
    get_perf_latency_metric,
    starter_timer,
    stream_metrics,
)
from angelia.api.shared_data import SharedData
from angelia.hermes.db import DB
from angelia.messaging.sender import send_message_to_hermes
from angelia.report import ctx

if TYPE_CHECKING:
    from angelia.resources.base_resource import Base
    from angelia.resources.loyalty_cards import LoyaltyCard


class HttpMethods(str, Enum):
    GET = "GET"


class AuthenticationMiddleware:
    def process_resource(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: "type[Base]",
        params: dict,
    ) -> None:
        try:
            auth_class = resource.auth_class
        except AttributeError:
            return  # no auth specified

        auth_instance = auth_class()
        req.context.auth_instance = auth_instance
        auth_instance.validate(req)


class AzureRefMiddleware:
    def process_resource(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: "type[Base]",
        params: dict,
    ) -> None:
        ctx.x_azure_ref = req.get_header("X-Azure-Ref")

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: "type[Base]",
        req_succeeded: bool,
    ) -> None:
        resp.set_header("X-Azure-Ref", ctx.x_azure_ref)


class SharedDataMiddleware:
    def process_resource(
        self, req: falcon.Request, resp: falcon.Response, resource: "type[Base]", params: dict
    ) -> None:
        SharedData(req, resp, resource, params)

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: "type[Base]",
        req_succeeded: bool,
    ) -> None:
        SharedData.delete_thread_vars()


class DatabaseSessionManager:
    """Middleware class to Manage sessions
    Falcon looks for existence of these methods"""

    def process_resource(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: "type[Base]",
        params: dict,
    ) -> None:
        DB().open()

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: "type[Base]",
        req_succeeded: bool,
    ) -> None:
        if db_session := DB().session:
            try:
                if req.method != HttpMethods.GET and not req_succeeded:
                    db_session.rollback()
                db_session.close()
            except AttributeError:
                return


class MetricMiddleware:
    """
    MetricMiddleware - Sends metrics in packets to a TCP endpoint
    """

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        starter_timer(req, time.time())

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: "type[Base]",
        req_succeeded: bool,
    ) -> None:
        now = time.time()
        metric_as_bytes = get_metrics_as_bytes(
            {
                "status": resp.status,
                "performance_latency": get_perf_latency_metric(req),
                "request_latency": get_latency_metric(req, now),
                "time_code": now,
                "end_point": req.path,
            }
        )

        stream_metrics(metric_as_bytes)


class FailureEventMiddleware:
    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        req.context.events_context = {}

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: "LoyaltyCard | type[Base]",
        req_succeeded: bool,
    ) -> None:
        if not req_succeeded and req.relative_uri == "/v2/loyalty_cards/add_trusted" and req.method == "POST":
            resource = cast("LoyaltyCard", resource)

            if handler := req.context.events_context.get("handler", None):
                hermes_message = {
                    "loyalty_plan_id": handler.loyalty_plan_id,
                    "loyalty_card_id": handler.card_id,
                    "user_id": handler.user_id,
                    "channel_slug": handler.channel_id,
                }
            else:
                user_id: int | None = None
                channel_slug: str | None = None
                try:
                    loyalty_plan_id = cast(
                        int | None,
                        getattr(req.context, "validated_media", req.media or {}).get("loyalty_plan_id", None),
                    )
                except Exception:
                    loyalty_plan_id = None
                with suppress(Exception):
                    user_id, channel_slug = cast(
                        tuple[int | None, str | None],
                        req.context.events_context.get("user_and_channel", resource.get_user_and_channel(req)),
                    )

                if not (user_id and loyalty_plan_id):
                    hermes_message = {}
                else:
                    hermes_message = {
                        "loyalty_plan_id": loyalty_plan_id,
                        "loyalty_card_id": None,
                        "user_id": user_id,
                        "channel_slug": channel_slug,
                    }

            if hermes_message:
                send_message_to_hermes("add_trusted_failed", hermes_message)

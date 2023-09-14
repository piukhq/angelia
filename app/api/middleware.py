import time
from enum import Enum
from typing import TYPE_CHECKING

import falcon

from app.api.helpers.metrics import (
    get_latency_metric,
    get_metrics_as_bytes,
    get_perf_latency_metric,
    starter_timer,
    stream_metrics,
)
from app.api.shared_data import SharedData
from app.hermes.db.session import scoped_db_session
from app.report import ctx

if TYPE_CHECKING:
    from app.resources.base_resource import Base


class HttpMethods(str, Enum):
    GET = "GET"


class AuthenticationMiddleware:
    def process_resource(
        self, req: falcon.Request, resp: falcon.Response, resource: "type[Base]", params: dict  # noqa: ARG002
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
        self, req: falcon.Request, resp: falcon.Response, resource: "type[Base]", params: dict  # noqa: ARG002
    ) -> None:
        ctx.x_azure_ref = req.get_header("X-Azure-Ref")

    def process_response(
        self, req: falcon.Request, resp: falcon.Response, resource: "type[Base]", req_succeeded: bool  # noqa: ARG002
    ) -> None:
        resp.set_header("X-Azure-Ref", ctx.x_azure_ref)


class SharedDataMiddleware:
    def process_resource(
        self, req: falcon.Request, resp: falcon.Response, resource: "type[Base]", params: dict
    ) -> None:
        SharedData(req, resp, resource, params)

    def process_response(
        self, req: falcon.Request, resp: falcon.Response, resource: "type[Base]", req_succeeded: bool  # noqa: ARG002
    ) -> None:
        SharedData.delete_thread_vars()


class DatabaseSessionManager:
    """Middleware class to Manage sessions
    Falcon looks for existence of these methods"""

    def process_response(
        self, req: falcon.Request, resp: falcon.Response, resource: "type[Base]", req_succeeded: bool  # noqa: ARG002
    ) -> None:
        if req.method != HttpMethods.GET and not req_succeeded:
            scoped_db_session.rollback()


class MetricMiddleware:
    """
    MetricMiddleware - Sends metrics in packets to a TCP endpoint
    """

    def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:  # noqa: ARG002
        starter_timer(req, time.time())

    def process_response(
        self, req: falcon.Request, resp: falcon.Response, resource: "type[Base]", req_succeeded: bool  # noqa: ARG002
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

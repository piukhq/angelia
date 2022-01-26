import time
from enum import Enum

import falcon

from app.api.helpers.metrics import (
    get_latency_metric,
    get_metrics_as_bytes,
    get_perf_latency_metric,
    starter_timer,
    stream_metrics,
)
from app.hermes.db import DB


class HttpMethods(str, Enum):
    GET = "GET"


class AuthenticationMiddleware:
    def process_resource(self, req: falcon.Request, resp: falcon.Response, resource: object, params: dict):
        try:
            auth_class = getattr(resource, "auth_class")
        except AttributeError:
            return  # no auth specified

        auth_instance = auth_class()
        req.context.auth_instance = auth_instance
        auth_instance.validate(req)


class DatabaseSessionManager:
    """Middleware class to Manage sessions
    Falcon looks for existence of these methods"""

    def process_resource(self, req: falcon.Request, resp: falcon.Response, resource: object, params: dict):
        # if req.method == HttpMethods.GET:
        DB().open_read()
        # else:
        #    DB().open_write()

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        req_succeeded: bool,
    ):
        db_session = DB().session
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

    def process_request(self, req: falcon.Request, resp: falcon.Response):
        starter_timer(req, time.time())

    def process_response(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        req_succeeded: bool,
    ):
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

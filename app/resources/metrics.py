from os import getenv

import falcon
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, Counter, generate_latest, multiprocess

from app.api.auth import NoAuth

from .base_resource import Base

loyalty_plan_get_counter = Counter(
    "loyalty_plan_get_requests", "Total loyal plan get requests.", ["endpoint", "channel", "response_status"]
)


class Metrics(Base):

    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response, **kwargs) -> None:
        registry = REGISTRY

        if getenv("PROMETHEUS_MULTIPROC_DIR"):
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)

        resp.text = generate_latest(registry)
        resp.set_header("Content-Type", CONTENT_TYPE_LATEST)
        resp.status = falcon.HTTP_200

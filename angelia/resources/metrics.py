from os import getenv
from typing import Any

import falcon
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, generate_latest, multiprocess

from angelia.api.auth import NoAuth
from angelia.resources.base_resource import Base


class Metrics(Base):
    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response, **kwargs: Any) -> None:  # noqa: ARG002
        registry = REGISTRY

        if getenv("PROMETHEUS_MULTIPROC_DIR"):
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)

        resp.text = generate_latest(registry)
        resp.set_header("Content-Type", CONTENT_TYPE_LATEST)
        resp.status = falcon.HTTP_200

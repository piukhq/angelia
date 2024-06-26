from typing import Any

import falcon
from kombu import Connection

from angelia.api.auth import NoAuth
from angelia.hermes.db import DB
from angelia.report import api_logger
from angelia.resources.base_resource import Base
from angelia.settings import settings


class ReadyZ(Base):
    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response, **kwargs: Any) -> None:  # noqa: ARG002
        pg = self._check_postgres()
        rb = self._check_rabbit()
        if pg and rb:
            resp.status = falcon.HTTP_204
        else:
            resp.status = falcon.HTTP_503
            resp.text = "Service Unavailable"

    def _check_postgres(self) -> bool:
        try:
            DB().engine.execute("SELECT 1").fetchone()
        except Exception as ex:
            healthy = False
            api_logger.error(ex)
        else:
            healthy = True
        return healthy

    def _check_rabbit(self) -> bool:
        try:
            with Connection(settings.RABBIT_DSN) as conn:
                conn.connect()
                available = conn.connected

        except Exception as ex:
            available = False
            api_logger.error(ex)

        return available

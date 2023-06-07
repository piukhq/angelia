from typing import Any, cast

import falcon
from kombu import Connection

from app.api.auth import NoAuth
from app.hermes.db import DB
from app.messaging.message_broker import BaseMessaging
from app.report import api_logger
from app.resources.base_resource import Base
from settings import RABBIT_DSN


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
            conn = cast(Connection, BaseMessaging(RABBIT_DSN).conn)
            conn.connect()
            available = conn.connected
            conn.close()
        except Exception as ex:
            available = False
            api_logger.error(ex)
        return available

import falcon

from app.api.auth import NoAuth
from app.api.helpers.vault import get_azure_client
from app.hermes.db import DB
from app.messaging.message_broker import BaseMessaging
from app.report import api_logger
from settings import RABBIT_DSN

from .base_resource import Base


class ReadyZ(Base):

    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        self.errors = []
        pg = self._check_postgres()
        rb = self._check_rabbit()
        az = self._check_secrets()
        if pg and rb and az:
            api_logger.info("Acording to ReadyZ; Angelia is all good.")
            resp.status = falcon.HTTP_204
        else:
            api_logger.info("Acording to ReadyZ; Angelia is broken.")
            api_logger.info("\n".join(self.errors))
            resp.status = falcon.HTTP_404

    def _check_postgres(self) -> bool:
        try:
            DB().engine.execute("SELECT 1").fetchone()
        except Exception as ex:
            healthy = False
            self.errors.append(ex)
        else:
            healthy = True
        return healthy

    def _check_rabbit(self) -> bool:
        try:
            conn = BaseMessaging(RABBIT_DSN).conn
            conn.connect()
            available = conn.connected
        except Exception as ex:
            self.errors.append(ex)
            available = False
        return available

    def _check_secrets(self) -> bool:
        try:
            secrets = get_azure_client()
            secrets.list_properties_of_secrets()
            available = True
        except Exception as ex:
            self.errors.append(ex)
            available = False
        return available

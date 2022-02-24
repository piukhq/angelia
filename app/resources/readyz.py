import falcon
from kombu import Connection

from app.api.auth import NoAuth
from app.hermes.db import DB
from settings import RABBIT_DSN

from .base_resource import Base


class ReadyZ(Base):

    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        self.errors = []
        pg = self._check_postgres()
        rb = self._check_rabbit()
        if pg and rb:
            resp.status = falcon.HTTP_204
        else:
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

    def _check_rabbit(self):
        try:
            conn = Connection(RABBIT_DSN)
            conn.connect()
            available = conn.connected
        except Exception as ex:
            self.errors.append(ex)
            available = False
        return available

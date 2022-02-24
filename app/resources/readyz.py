from xmlrpc.client import boolean
import falcon

from app.api.auth import NoAuth
from settings import RABBIT_DSN

from .base_resource import Base

from app.hermes.db import DB

from kombu import Connection

class ReadyZ(Base):

    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        self.errors = []
        pg = self._check_postgres()
        rb = self._check_rabbit()
        if pg and rb:
            resp.status = falcon.HTTP_204
        else:
            ## check which response is more sensible 
            resp.status = falcon.HTTP_404

    def _check_postgres(self) -> boolean:
        try:
            DB().engine.execute("SELECT 1").fetchone()
        except Exception as ex:
            healthy = False
            self.errors.append(ex)
        else:
            healthy = True
        return healthy

    def _check_rabbit(self):        
        conn = Connection(RABBIT_DSN)# example 'amqp://guest:guest@localhost:5672/'
        conn.connect()
        client = conn.get_manager()
        queues = client.get_queues('/')#assuming vhost as '/'
        print(queues)
        return True

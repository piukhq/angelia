import falcon

from app.api.auth import NoAuth
from .base_resource import Base


class LiveZ(Base):

    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.status = falcon.HTTP_204

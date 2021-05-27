import falcon
from .base_resource import Base
from app.api.auth import NoAuth


class HealthZ(Base):

    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"ok": True}

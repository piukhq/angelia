import falcon
from .base_resource import Base


class HealthZ(Base):

    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"ok": True}

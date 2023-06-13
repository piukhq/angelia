from typing import Any

import falcon

from app.api.auth import NoAuth
from app.resources.base_resource import Base


class LiveZ(Base):
    auth_class = NoAuth

    def on_get(self, req: falcon.Request, resp: falcon.Response, **kwargs: Any) -> None:  # noqa: ARG002
        resp.status = falcon.HTTP_204

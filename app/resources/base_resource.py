from typing import TYPE_CHECKING, Any

import falcon

from app.api.auth import AccessToken, BaseAuth

if TYPE_CHECKING:
    from falcon import App
    from sqlalchemy.orm import Session


def method_err(req: falcon.Request) -> dict:
    return {
        "title": f"{req.method} request to '{req.relative_uri}' Not Implemented",
        "description": "Request made to the wrong method of an existing resource",
    }


class Base:
    auth_class: type[BaseAuth] = AccessToken

    def __init__(self, app: "App", prefix: str, url: str, kwargs: dict, db_session: "Session") -> None:  # noqa: PLR0913
        app.add_route(f"{prefix}{url}", self, **kwargs)
        self.session = db_session

    def on_get(self, req: falcon.Request, resp: falcon.Response, **kwargs: Any) -> None:  # noqa: ARG002
        raise falcon.HTTPBadRequest(**method_err(req))

    def on_post(self, req: falcon.Request, resp: falcon.Response, **kwargs: Any) -> None:  # noqa: ARG002
        raise falcon.HTTPBadRequest(**method_err(req))

    def on_delete(self, req: falcon.Request, resp: falcon.Response, **kwargs: Any) -> None:  # noqa: ARG002
        raise falcon.HTTPBadRequest(**method_err(req))

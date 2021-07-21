import falcon
import voluptuous

from app.api.auth import BinkJWTs
from app.api.exceptions import ValidationError


def validate_input(req, resp, resource, params, input_validator):
    assert (
        input_validator is not None
    ), f"A valid schema is required to validate input for '{resource.__class__.__name__}' resource"
    assert isinstance(
        input_validator, voluptuous.Schema
    ), f"Expected input_validator of type voluptuous.Schema for '{resource.__class__.__name__}' resource"

    try:
        input_validator(req.data)
    except voluptuous.MultipleInvalid as e:
        raise ValidationError(e.errors)


def method_err(req: falcon.Request):
    return {
        "title": f"{req.method} request to '{req.relative_uri}' Not Implemented",
        "description": "Request made to the wrong method of an existing resource",
    }


class Base:

    auth_class = BinkJWTs

    def __init__(self, app, prefix, url, kwargs, db):
        app.add_route(f"{prefix}{url}", self, **kwargs)
        self.db = db

    @property
    def session(self):
        """
        Syntactic sugar saves having to import DB and writing DB().session for each query
        instead within a resource can use self.session

        The middleware opens and closes sessions and dynamically changes from read to write depending on request
        hence we cannot store the session in init and must create it from the DB() singleton passed in init
        """
        return self.db.session

    def on_get(self, req: falcon.Request, resp: falcon.Response, **kwargs) -> None:
        raise falcon.HTTPBadRequest(**method_err(req))

    def on_post(self, req: falcon.Request, resp: falcon.Response, **kwargs) -> None:
        raise falcon.HTTPBadRequest(**method_err(req))

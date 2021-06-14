import falcon
from app.api.auth import BinkJWTs

# @todo Override the Falcon Base Error Classes to log errors


def method_err(req: falcon.Request):
    return{
        'title': f"{req.method} request to '{req.relative_uri}' Not Implemented",
        'description': 'Request made to the wrong method of an existing resource'
    }


class Base:

    auth_class = BinkJWTs

    def __init__(self, app, prefix, url, db):
        app.add_route(f"{prefix}{url}", self)
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



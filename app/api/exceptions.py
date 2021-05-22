import falcon


class AuthenticationError(falcon.HTTPUnauthorized):
    pass


class ValidationError(falcon.HTTPBadRequest):
    pass

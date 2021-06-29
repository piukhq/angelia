import falcon

from app.api.exceptions import AuthenticationError


def get_authenticated_user(req: falcon.Request):
    params = getattr(req.context, "authenticated")
    user_id = params.get("user_id", None)
    if not user_id:
        raise AuthenticationError()
    return user_id


def get_authenticated_channel(req: falcon.Request):
    params = getattr(req.context, "authenticated")
    channel_id = params.get("channel_id", None)
    if not channel_id:
        raise AuthenticationError()
    return channel_id


class NoAuth:
    def validate(self, reg: falcon.Request):
        return {}


class BinkJWTs:
    def validate(self, reg: falcon.Request):
        """
        @todo add jwt validate for Bearer and token ie Bink or Barclays
        Check signature against bundle_id
        No need to check contents as they are validated by gets see above
        hence access to resource is granted if class defined in resource vaslidate
        """

        return {"user_id": 457, "channel_id": 300}

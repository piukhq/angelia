import falcon

from app.api.metrics import Metric
from app.api.validators import magic_link_access_token_schema, validate
from app.handlers.magic_link import MagicLinkHandler
from app.resources.base_resource import Base


class MagicLink(Base):
    @validate(req_schema=magic_link_access_token_schema)
    def on_post_access_token(self, req: falcon.Request, resp: falcon.Response) -> None:
        tmp_token = req.media.get("token")

        resp.media = MagicLinkHandler(db_session=self.session).get_or_create_user(tmp_token)
        resp.status = falcon.HTTP_202

        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

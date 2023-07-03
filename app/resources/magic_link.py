import falcon

from app.api.auth import NoAuth
from app.api.metrics import Metric
from app.api.validators import magic_link_access_token_schema, magic_link_email_schema, validate
from app.handlers.magic_link import MagicLinkHandler
from app.resources.base_resource import Base


class MagicLink(Base):
    auth_class = NoAuth

    @validate(req_schema=magic_link_email_schema)
    def on_post_email(self, req: falcon.Request, resp: falcon.Response) -> None:
        email = req.media["email"]
        slug = req.media["slug"]
        locale = req.media["locale"]
        bundle_id = req.media["bundle_id"]

        resp.media = MagicLinkHandler(db_session=self.session).send_magic_link_email(email, slug, locale, bundle_id)
        resp.status = falcon.HTTP_202

        metric = Metric(request=req, status=resp.status)
        metric.route_metric()


class MagicLinkAuth(Base):
    @validate(req_schema=magic_link_access_token_schema)
    def on_post_access_token(self, req: falcon.Request, resp: falcon.Response) -> None:
        tmp_token = req.media.get("token")

        resp.media = MagicLinkHandler(db_session=self.session).get_or_create_user(tmp_token)
        resp.status = falcon.HTTP_202

        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

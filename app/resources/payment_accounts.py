import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.metrics import Metric
from app.api.serializers import PaymentCardSerializer
from app.api.validators import empty_schema, payment_accounts_add_schema, payment_accounts_update_schema, validate
from app.encryption import decrypt_payload
from app.handlers.payment_account import PaymentAccountHandler, PaymentAccountUpdateHandler
from app.report import log_request_data
from app.resources.base_resource import Base


class PaymentAccounts(Base):
    @decrypt_payload
    @log_request_data
    @validate(req_schema=payment_accounts_add_schema, resp_schema=PaymentCardSerializer)
    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        payment_account_handler = PaymentAccountHandler(
            db_session=self.session, user_id=user_id, channel_id=channel, **req.context.validated_media
        )
        resp_data, created = payment_account_handler.add_card()

        resp.media = resp_data
        resp.status = falcon.HTTP_201 if created else falcon.HTTP_200
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @decrypt_payload
    @log_request_data
    @validate(req_schema=payment_accounts_update_schema, resp_schema=PaymentCardSerializer)
    def on_patch_by_id(self, req: falcon.Request, resp: falcon.Response, payment_account_id: int) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        media = req.context.validated_data

        payment_account_update_handler = PaymentAccountUpdateHandler(
            db_session=self.session, user_id=user_id, channel_id=channel, account_id=payment_account_id, **media
        )
        resp_data = payment_account_update_handler.update_card(update_fields=media.keys())

        resp.media = resp_data
        resp.status = falcon.HTTP_200
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @validate(req_schema=empty_schema)
    def on_delete_by_id(self, req: falcon.Request, resp: falcon.Response, payment_account_id: int) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        PaymentAccountHandler.delete_card(self.session, channel, user_id, payment_account_id)

        resp.status = falcon.HTTP_202
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

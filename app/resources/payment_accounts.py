import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.serializers import PaymentCardSerializer
from app.api.validators import payment_accounts_schema, validate
from app.handlers.payment_account import PaymentAccountHandler
from app.report import log_request_data
from app.resources.base_resource import Base


class PaymentAccounts(Base):
    @log_request_data
    @validate(req_schema=payment_accounts_schema, resp_schema=PaymentCardSerializer)
    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)

        payment_account_handler = PaymentAccountHandler(
            db_session=self.session, user_id=user_id, channel_id=channel, **req.media
        )
        resp_data, created = payment_account_handler.add_card()

        resp.media = resp_data
        resp.status = falcon.HTTP_201 if created else falcon.HTTP_200

    def on_delete_by_id(self, req: falcon.Request, resp: falcon.Response, payment_account_id: int) -> None:

        channel = get_authenticated_channel(req)
        user_id = get_authenticated_user(req)

        PaymentAccountHandler.delete_card(self.session, channel, user_id, payment_account_id)

        resp.status = falcon.HTTP_202

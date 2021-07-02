import falcon

from app.api.auth import get_authenticated_user, get_authenticated_channel
from app.api.serializers import PaymentCardSerializer
from app.api.validators import validate, payment_accounts_schema
from app.handlers.payment_account import PaymentAccountHandler

from .base_resource import Base


class PaymentAccounts(Base):
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

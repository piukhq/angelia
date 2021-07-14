import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.serializers import PaymentCardSerializer
from app.api.validators import payment_accounts_schema, validate
from app.handlers.payment_account import PaymentAccountHandler
from app.hermes.models import PaymentAccountUserAssociation
from app.messaging.sender import send_message_to_hermes

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

    def on_delete(self, req: falcon.Request, resp: falcon.Response, payment_account_id=None) -> None:
        channel = get_authenticated_channel(req)
        user_id = get_authenticated_user(req)
        print(user_id)

        message_data = {'channel': channel,
                        'user_id': user_id}

        if not payment_account_id:
            # throw error/return unsuccessful
            pass

        accounts = (
            self.session.query(PaymentAccountUserAssociation)
                .filter(
                PaymentAccountUserAssociation.payment_card_account_id == payment_account_id,
                PaymentAccountUserAssociation.user_id == user_id,
            ).all()
        )

        if len(accounts) < 1:
            # throw error /return unsuccessful
            resp.status = falcon.HTTP_404
        else:
            message_data['payment_card_account_id'] = payment_account_id
            resp.status = falcon.HTTP_202
            send_message_to_hermes("delete_payment_account", message_data)

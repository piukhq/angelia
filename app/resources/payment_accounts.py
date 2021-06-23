import falcon
from .base_resource import Base
from app.hermes.models import User, Channel, PaymentAccountUserAssociation, PaymentAccount
from sqlalchemy import insert
from app.api.auth import get_authenticated_user, get_authenticated_channel
from app.messaging.sender import send_message_to_hermes
from datetime import datetime


class PaymentAccounts(Base):

    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        post_data = req.media

        data = {}
        request_fields = ['expiry_month',
                          'expiry_year',
                          'name_on_card',
                          'issuer', 'token',
                          'last_four_digits',
                          'first_six_digits',
                          'fingerprint',
                          'provider',
                          'type',
                          'country',
                          'currency_code']

        compare_fields = ['expiry_month', 'expiry_year', 'name_on_card', ]

        try:
            for field in request_fields:
                data[field] = post_data[field]
        except(KeyError, AttributeError):
            raise falcon.HTTPBadRequest('Missing parameters')

        existing_accounts = self.session.query(PaymentAccount, User)\
            .select_from(PaymentAccount)\
            .join(PaymentAccountUserAssociation)\
            .join(User)\
            .filter(PaymentAccount.fingerprint == data['fingerprint'])\
            .all()

        linked_users = []
        compare_details = {}

        for account in existing_accounts:
            print(account.PaymentAccount.fingerprint)
            linked_users.append(account.User.id)
            compare_details['expiry_month']


        if len(existing_accounts) > 0:
            if user_id in linked_users:
                if data['expiry_month']
            else:
                print("ACCOUNT EXISTS IN ANOTHER WALLET - LINK THIS USER")


        else:
            print("THIS IS A NEW ACCOUNT")






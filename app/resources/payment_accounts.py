import falcon
from .base_resource import Base
from app.hermes.models import User, Channel, PaymentAccountUserAssociation, PaymentAccount
from sqlalchemy import insert, update
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
        compare_fields = {}

        if len(existing_accounts) > 1:
            print("TOO MANY ACCOUNTS WITH THIS FINGERPRINT!")

        elif len(existing_accounts) == 1:

            existing_payment_account = existing_accounts[0].PaymentAccount

            print(existing_accounts[0].PaymentAccount.fingerprint)
            linked_users.append(existing_accounts[0].User.id)
            compare_fields['expiry_month'] = existing_payment_account.expiry_month
            compare_fields['expiry_year'] = existing_payment_account.expiry_year
            compare_fields['name_on_card'] = existing_payment_account.name_on_card

            if user_id in linked_users:
                if self.fields_match_existing(data, compare_fields):
                    print("RETURN EXISTING ACCOUNT DETAILS")
                    details = self.payment_account_info_to_dict(existing_payment_account)
                    resp.body = details
                    resp.status = falcon.HTTP_200
                else:
                    print("UPDATE EXISTING ACCOUNT DETAILS WITH NEW INFORMATION")

                    self.session.update(PaymentAccount)\
                        .where(PaymentAccount.id == existing_payment_account.id)\
                        .values(expiry_month=existing_payment_account.expiry_month,
                                expiry_year=existing_payment_account.expiry_year,
                                name_on_card=existing_payment_account.name_on_card)

                    self.session.commit()
                    details = self.payment_account_info_to_dict(existing_payment_account)
                    resp.body = details
                    resp.status = falcon.HTTP_200

            else:
                print("ACCOUNT EXISTS IN ANOTHER WALLET - LINK THIS USER")
                self.session.insert()

        else:
            print("THIS IS A NEW ACCOUNT")

    @staticmethod
    def fields_match_existing(self, data, compare_details):

        fields_alike = True

        for key, value in compare_details:
            if data[key] != compare_details[key]:
                fields_alike = False

        return fields_alike

    @staticmethod
    def payment_account_info_to_dict(self, existing_payment_account:PaymentAccount):

        details = {"expiry_month": existing_payment_account.expiry_month,
                   "expiry_year": existing_payment_account,
                   "name_on_card": existing_payment_account.name_on_card,
                   "issuer": existing_payment_account.issuer_id,
                   "id": existing_payment_account.id,
                   "status": existing_payment_account.status
                   }

        return details





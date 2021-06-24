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

        print(data)

        existing_accounts = self.session.query(PaymentAccount, User)\
            .select_from(PaymentAccount)\
            .join(PaymentAccountUserAssociation)\
            .join(User)\
            .filter(PaymentAccount.fingerprint == data['fingerprint'])\
            .all()

        for account in existing_accounts:
            print(account)

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

                    statement_update_existing_account = update(PaymentAccount)\
                        .where(PaymentAccount.id == existing_payment_account.id)\
                        .values(expiry_month=existing_payment_account.expiry_month,
                                expiry_year=existing_payment_account.expiry_year,
                                name_on_card=existing_payment_account.name_on_card)

                    self.session.execute(statement_update_existing_account)
                    self.session.commit()
                    details = self.payment_account_info_to_dict(existing_payment_account)
                    resp.body = details
                    resp.status = falcon.HTTP_200

            else:
                print("ACCOUNT EXISTS IN ANOTHER WALLET - LINK THIS USER")
                statement_link_existing_to_user = insert(PaymentAccountUserAssociation)\
                    .values(payment_card_account_id=existing_payment_account.id,
                            user_id=user_id)
                self.session.execute(statement_link_existing_to_user)
                self.session.commit()

        else:
            print("THIS IS A NEW ACCOUNT")
            statement_create_new_payment_account = insert(PaymentAccount)\
            .values(
                name_on_card=data['name_on_card'],
                expiry_month=data['expiry_month'],
                expiry_year=data['expiry_year'],
                status=0,
                order=0,
                created=datetime.now(),
                updated=datetime.now(),
                issuer_id=3,
                payment_card_id=1,
                token=data['token'],
                country='UK',
                currency_code=data['currency_code'],
                pan_end=data['last_four_digits'],
                pan_start=data['first_six_digits'],
                is_deleted=False,
                fingerprint=data['fingerprint'],
                psp_token=data['token'],
                consents=[],
                formatted_images={},
                pll_links=[],
                agent_data={}
            )

            new_payment_account = self.session.execute(statement_create_new_payment_account)

            statement_link_existing_to_user = insert(PaymentAccountUserAssociation) \
                .values(payment_card_account_id=new_payment_account.inserted_primary_key[0],
                        user_id=user_id)
            self.session.execute(statement_link_existing_to_user)

            self.session.commit()

            print('Added new PaymentAccount: ' + str(new_payment_account.inserted_primary_key[0]))


    def fields_match_existing(self, data: dict, compare_details: dict):

        fields_alike = True

        for key, value in compare_details:
            if data[key] != compare_details[key]:
                fields_alike = False

        return fields_alike

    def payment_account_info_to_dict(self, existing_payment_account:PaymentAccount):

        details = {"expiry_month": existing_payment_account.expiry_month,
                   "expiry_year": existing_payment_account,
                   "name_on_card": existing_payment_account.name_on_card,
                   "issuer": existing_payment_account.issuer_id,
                   "id": existing_payment_account.id,
                   "status": existing_payment_account.status
                   }

        return details





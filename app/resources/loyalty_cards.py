import falcon
from .base_resource import Base
from app.hermes.models import SchemeAccountUserAssociation, SchemeAccount, Scheme, SchemeChannelAssociation, \
    SchemeCredentialQuestion, SchemeAccountCredentialAnswer, Channel
from sqlalchemy import select, insert
from app.api.auth import get_authenticated_user, get_authenticated_channel
from app.messaging.sender import send_message_to_hermes
from datetime import datetime


class LoyaltyAdds(Base):

    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        post_data = req.media
        print("user_id = " + str(user_id))
        print("channel = " + str(channel))

        try:
            plan = post_data['loyalty_plan']
            adds = post_data['account'].get('add_fields', [])
            auths = post_data['account'].get('authorise_fields', [])
        except(KeyError, AttributeError):
            raise falcon.HTTPBadRequest("missing parameters")

        print(plan, adds, auths)

        # Checks that Scheme is available to this channel and has an active link, then returns all credential questions
        # for this Scheme.
        credential_questions = self.session.query(SchemeCredentialQuestion, Scheme, SchemeChannelAssociation, Channel)\
            .select_from(SchemeCredentialQuestion)\
            .join(Scheme)\
            .join(SchemeChannelAssociation)\
            .join(Channel)\
            .filter(SchemeCredentialQuestion.scheme_id == plan)\
            .filter(Channel.bundle_id == channel)\
            .filter(SchemeChannelAssociation.status == 0)

        cred_names = []
        for question in credential_questions:
            cred_names.append(question.SchemeCredentialQuestion.label)

        all_creds = []

        for cred in adds:
            if cred['credential_slug'] not in cred_names:
                print("CRED REJECTED")
            else:
                print("CRED FINE")
                all_creds.append(cred['value'])

        for cred in auths:
            if cred['credential_slug'] not in cred_names:
                print("CRED REJECTED")
            else:
                print("CRED FINE")
                all_creds.append(cred['value'])

        # Returns all credential answers which match the given Scheme and any of the credential answers provided
        # in the request. If nothing is returned, then no match for given credential answers is found and we will
        # create a new Scheme Account.
        # Currently this checks if any (not all) credential(s) given is in the table - we may want to reduce
        # this to one specific cred, or force it to return only if all creds are the same (or we can perform that check
        # in logic here.)
        matching_creds = self.session.query(SchemeAccountCredentialAnswer)\
            .join(SchemeCredentialQuestion)\
            .filter(SchemeCredentialQuestion.scheme_id == plan)\
            .filter(SchemeAccountCredentialAnswer.answer.in_(all_creds)).all()

        print(cred_names)
        print(all_creds)

        # If matching credentials are found, we should now check that the scheme accounts to which those credentials
        # belong are in the current wallet (i.e. the current user)
        if len(matching_creds) > 0:

            matching_cred_scheme_accounts = []

            for cred in matching_creds:
                print(cred.question_id, cred.answer, cred.scheme_account_id)
                matching_cred_scheme_accounts.append(cred.scheme_account_id)

            # Returns SchemeAccount objects for every SchemeAccount where credentials match the credentials given,
            # AND where this is linked to the current user (i.e. in the current wallet). We may want to add other
            # conditions to this, such as filtering out SchemeAccounts with is_deleted = True.
            matching_user_scheme_accounts = self.session.query(SchemeAccount)\
                .join(SchemeAccountUserAssociation)\
                .filter(SchemeAccountUserAssociation.user_id == user_id)\
                .filter(SchemeAccount.id.in_(matching_cred_scheme_accounts)).all()

            """
            IF matching_creds returns values but matching_user_scheme_account does not, then account exists in another 
            wallet.
            IF matching_creds returns values AND matching_user_scheme_account returns values, then these creds are for 
            an existing account in this wallet.
            IF matching_creds is None, then this is a new card and should follow the add journey."""

            for scheme_account in matching_user_scheme_accounts:
                print(scheme_account.id)

            if len(matching_user_scheme_accounts) > 0:
                print("THIS IS AN EXISTING ACCOUNT ALREADY IN THIS WALLET")

            else:
                print("WE SHOULD LINK THIS USER TO THE MATCHING SCHEME ACCOUNT(S)")

                objects_to_insert = []
                for scheme_account in matching_cred_scheme_accounts:
                    objects_to_insert.append(SchemeAccountUserAssociation(scheme_account_id=scheme_account.id, user_id=user_id))

                self.session.bulk_save_objects(objects_to_insert)
                self.session.commit()


        else:
            print("WE SHOULD ADD A NEW SCHEME ACCOUNT IN THIS WALLET")

            statement = insert(SchemeAccount).values(status=1, order=1, created=datetime.now(), updated=datetime.now(), card_number='1234', barcode='1234', main_answer='1234', scheme_id=plan, is_deleted=False)

            new_row = self.session.execute(statement)

            print (new_row.inserted_primary_key)

            self.session.commit()


    # Returns in 131 ms (1st time) > 39 ms (2nd time)

        send_message_to_hermes("add_card", {"plan": plan})
        loyalty_cards = []
        adds = []

        reply = [
            {"adds": adds},
            {"loyalty_cards": loyalty_cards},

        ]

        resp.media = reply

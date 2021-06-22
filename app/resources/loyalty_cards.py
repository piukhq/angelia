import falcon
from .base_resource import Base
from app.hermes.models import SchemeAccountUserAssociation, SchemeAccount, Scheme, SchemeChannelAssociation, \
    SchemeCredentialQuestion, SchemeAccountCredentialAnswer, Channel
from sqlalchemy import select
from app.api.auth import get_authenticated_user, get_authenticated_channel
from app.messaging.sender import send_message_to_hermes


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


        # Returns all credential answers which match the given scheme and any of the credential answers provided in the request.
        # If returns nothing then no match for given credential answers is found, and we create a new Scheme Account.
        # Currently this returns if any credential given is in the table - we may want to reduce this to one specific cred.

        matching_creds = self.session.query(SchemeAccountCredentialAnswer)\
            .join(SchemeCredentialQuestion)\
            .filter(SchemeCredentialQuestion.scheme_id == plan)\
            .filter(SchemeAccountCredentialAnswer.answer.in_(all_creds)).all()

        print(cred_names)
        print(all_creds)

        """    
                IF no matching credentials are returned, then ADD card (ADD journey) (INSERT New entry into database with correct information)

                IF there are matching credentials:
                1. Check if card is in this user's wallet.
                2. IF YES
                3. IF NO Link user to existing scheme account

                """

        if len(matching_creds) > 0:

            matching_cred_scheme_accounts = []

            for cred in matching_creds:
                print(cred.question_id, cred.answer, cred.scheme_account_id)
                matching_cred_scheme_accounts.append(cred.scheme_account_id)

            # Returns SchemeAccount objects for every SchemeAccount where credentials match the credentials given,
            # AND where this is linked to the current user (i.e. in the current wallet).
            matching_user_scheme_accounts = self.session.query(SchemeAccount)\
                .join(SchemeAccountUserAssociation)\
                .filter(SchemeAccountUserAssociation.user_id == user_id)\
                .filter(SchemeAccount.id.in_(matching_cred_scheme_accounts)).all()

        # if matching_creds returns values but matching_user_scheme_account does not, then account exists in another wallet
        # if matching_creds is not None and matching_user_scheme_account is not None, then these creds are for an existing account in this wallet.
        # if matching_creds is None, then this is a new card and should follow the add journey.

            for scheme_account in matching_user_scheme_accounts:
                print(scheme_account.id)

            if len(matching_user_scheme_accounts) > 0:
                print ("THIS IS AN EXISTING ACCOUNT ALREADY IN THIS WALLET")

            else:
                print ("WE SHOULD LINK THIS USER TO THE MATCHING SCHEME ACCOUNT(S)")






        """
        existing_accounts = self.session.query(SchemeAccountUserAssociation, Scheme, SchemeAccount,
                                               SchemeCredentialQuestion, SchemeAccountCredentialAnswer,
                                               SchemeChannelAssociation) \
            .select_from(SchemeAccountUserAssociation) \
            .filter(SchemeAccountUserAssociation.user_id == user_id) \
            .filter(Scheme.id == plan)\
            .join(SchemeAccount)\
            .join(Scheme, SchemeAccount.scheme_id == Scheme.id)\
            .join(SchemeChannelAssociation)\
            .join(SchemeCredentialQuestion) \
            .join(SchemeAccountCredentialAnswer,
                  (SchemeAccount.id == SchemeAccountCredentialAnswer.scheme_account_id) &
                  (SchemeCredentialQuestion.id == SchemeAccountCredentialAnswer.question_id), isouter=True).all()
                  """
        """
        .add_columns(
            SchemeAccount.id.label("scheme_account_id"),
            SchemeAccount.is_deleted.label("scheme_account_is_deleted"),
            SchemeAccount.status.label("scheme_account_status"),
            SchemeCredentialQuestion.id.label("scheme_credential_question_id"),
            SchemeCredentialQuestion.label.label("scheme_credential_question_label"),
            SchemeAccountCredentialAnswer.answer.label("scheme_account_credential_answer"),
            SchemeAccountCredentialAnswer.question_id.label("scheme_account_credential_answer_question_id"),
            SchemeAccountCredentialAnswer.scheme_account_id.label("scheme_account_credential_answer_scheme_account_id"),
            Scheme.id.label("scheme_id"),
            Scheme.name.label("scheme_name"),
        )

        questions = []

        for i in existing_accounts:
            if i.SchemeCredentialQuestion.label not in questions:
                questions.append(i.SchemeCredentialQuestion.label)

                print (i)

        for i in existing_accounts:
            try:
                answer = i.SchemeAccountCredentialAnswer.answer
            except AttributeError:
                answer = "NULL"

            data = {"scheme_account_id": i.SchemeAccount.id,
                    "scheme_account_status:": i.SchemeAccount.status,
                    "scheme_id": i.Scheme.id,
                    "scheme_slug": i.Scheme.name,
                    "scheme_credential_questions": questions,
                    "scheme_account_credential_answer": answer
                    }

            print(data)
"""
        send_message_to_hermes("add_card", {"plan": plan})
        loyalty_cards = []
        adds = []

        reply = [
            {"adds": adds},
            {"loyalty_cards": loyalty_cards},

        ]

        resp.media = reply

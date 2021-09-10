# from datetime import datetime

import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user
from app.api.serializers import LoyaltyCardSerializer
from app.api.validators import loyalty_card_add_and_auth_schema, loyalty_card_add_schema, loyalty_card_add_and_register_schema, validate
from app.handlers.loyalty_card import ADD, ADD_AND_AUTHORISE, ADD_AND_REGISTER, LoyaltyCardHandler
from app.report import ctx, log_request_data

from .base_resource import Base

# from sqlalchemy import insert

# from app.hermes.models import (
#     Channel,
#     Scheme,
#     SchemeAccount,
#     SchemeAccountCredentialAnswer,
#     SchemeAccountUserAssociation,
#     SchemeChannelAssociation,
#     SchemeCredentialQuestion,
# )
# from app.messaging.sender import send_message_to_hermes


class LoyaltyCard(Base):
    def get_handler(self, req: falcon.Request, journey) -> get_authenticated_user:
        user_id = ctx.user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        handler = LoyaltyCardHandler(
            db_session=self.session,
            user_id=user_id,
            channel_id=channel,
            journey=journey,
            loyalty_plan_id=req.media["loyalty_plan"],
            all_answer_fields=req.media["account"],
        )
        return handler

    @log_request_data
    @validate(req_schema=loyalty_card_add_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD)
        created = handler.add_card_to_wallet()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_201 if created else falcon.HTTP_200

    @log_request_data
    @validate(req_schema=loyalty_card_add_and_auth_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add_and_auth(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD_AND_AUTHORISE)
        created = handler.add_auth_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if created else falcon.HTTP_200

    @log_request_data
    @validate(req_schema=loyalty_card_add_and_register_schema, resp_schema=LoyaltyCardSerializer)
    def on_post_add_and_register(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        handler = self.get_handler(req, ADD_AND_REGISTER)
        created = handler.add_auth_card()
        resp.media = {"id": handler.card_id}
        resp.status = falcon.HTTP_202 if created else falcon.HTTP_200


class LoyaltyCardAuthorise(Base):
    def on_post(self, req: falcon.Request, resp: falcon.Response, *args) -> None:
        pass
        # Todo: commenting out as reference for when this endpoint is implemented fully
        # user_id = get_authenticated_user(req)
        # channel = get_authenticated_channel(req)
        # post_data = req.media
        # print("user_id = " + str(user_id))
        # print("channel = " + str(channel))
        #
        # try:
        #     plan = post_data["loyalty_plan"]
        #     adds = post_data["account"].get("add_fields", [])
        #     auths = post_data["account"].get("authorise_fields", [])
        # except (KeyError, AttributeError):
        #     raise falcon.HTTPBadRequest("Missing Credentials - Add and Authorise credentials required")
        #
        # print(f"scheme_id = {plan}")
        #
        # add_and_auth_creds = adds + auths
        # print(f"Provided credentials: {add_and_auth_creds}")
        #
        # # --------------Checks Credentials--------------
        #
        # # Checks that Scheme is available to this channel and has an active link, then returns all credential
        # questions for this Scheme.
        # credential_questions = (
        #     self.session.query(SchemeCredentialQuestion, Scheme, SchemeChannelAssociation, Channel)
        #     .select_from(SchemeCredentialQuestion)
        #     .join(Scheme)
        #     .join(SchemeChannelAssociation)
        #     .join(Channel)
        #     .filter(SchemeCredentialQuestion.scheme_id == plan)
        #     .filter(Channel.bundle_id == channel)
        #     .filter(SchemeChannelAssociation.status == 0)
        # )
        #
        # # Creates a list of dictionaries containing each Scheme question's id, label and type..
        # # Also adds to required_scheme_question it's an auth or add field
        # required_scheme_questions = []
        # all_scheme_questions = {}
        # all_answers = []
        #
        # for question in credential_questions:
        #     all_scheme_questions[question.SchemeCredentialQuestion.label] = {
        #         "question_id": question.SchemeCredentialQuestion.id,
        #         "type": question.SchemeCredentialQuestion.type,
        #         "manual_question": question.SchemeCredentialQuestion.manual_question,
        #     }
        #     if (
        #         question.SchemeCredentialQuestion.add_field is True
        #         or question.SchemeCredentialQuestion.auth_field is True
        #     ):
        #         required_scheme_questions.append(question.SchemeCredentialQuestion.label)
        #
        # print(f"Scheme Questions: {all_scheme_questions}")
        #
        # # Checks provided credential slugs against possible credential question slugs.
        # # If this is a required field (auth or add), then this is removed from list of required fields
        # # and 'ticked off'.
        #
        # for cred in add_and_auth_creds:
        #     if cred["credential_slug"] not in list(all_scheme_questions.keys()):
        #         raise falcon.HTTPBadRequest("Invalid credential slug(s) provided")
        #     else:
        #         all_answers.append(cred["value"])
        #         if cred["credential_slug"] in required_scheme_questions:
        #             required_scheme_questions.remove(cred["credential_slug"])
        #
        # # If there are remaining auth or add fields (i.e. not all add/auth answers have been provided, ERROR.
        # if required_scheme_questions:
        #     raise falcon.HTTPBadRequest("Not all required credentials have been provided")
        #
        # # --------------Checks for existing Scheme Account(s)--------------
        #
        # # Returns all credential answers for the given Scheme AND associated with an active SchemeAccount
        # # which match any of the provided credential values. If nothing is returned, then we will create a new Scheme
        # # Account.
        # # Currently this checks if any (not all) of the credential(s) given are in the table - we may want to reduce
        # # this to one specific cred, or force it to return only if all credentials are matched (or we can perform that
        # # check in logic here.)
        # matching_answers = (
        #     self.session.query(SchemeAccountCredentialAnswer)
        #     .join(SchemeCredentialQuestion)
        #     .join(SchemeAccount)
        #     .filter(SchemeCredentialQuestion.scheme_id == plan)
        #     .filter(SchemeAccountCredentialAnswer.answer.in_(all_answers))
        #     .filter(SchemeAccount.is_deleted == "false")
        #     .all()
        # )
        #
        # print(all_answers)
        #
        # # If matching credentials are found, we should now check that the scheme accounts to which those credentials
        # # belong are in the current wallet (i.e. the current user)
        #
        # # --------------IF matching credentials are found:--------------
        #
        # if len(matching_answers) > 0:
        #
        #     matching_cred_scheme_accounts = []
        #
        #     for answer in matching_answers:
        #         print(answer.question_id, answer.answer, answer.scheme_account_id)
        #
        #         if answer.scheme_account_id not in matching_cred_scheme_accounts:
        #             matching_cred_scheme_accounts.append(answer.scheme_account_id)
        #
        #     # Returns SchemeAccount objects for every SchemeAccount where credentials match the credentials given,
        #     # Scheme Account is not deleted, AND where this is linked to the current user
        #     # (i.e. in the current wallet). We may want to add other conditions to this going forwards.
        #     matching_user_scheme_accounts = (
        #         self.session.query(SchemeAccount)
        #         .join(SchemeAccountUserAssociation)
        #         .filter(SchemeAccountUserAssociation.user_id == user_id)
        #         .filter(SchemeAccount.id.in_(matching_cred_scheme_accounts))
        #         .filter(SchemeAccount.is_deleted == "false")
        #         .all()
        #     )
        #
        #     """
        #     IF matching_creds returns values but matching_user_scheme_account does not, then account exists in another
        #     wallet.
        #     IF matching_creds returns values AND matching_user_scheme_account returns values, then these creds are for
        #     an existing account in this wallet.
        #     IF matching_creds is None, then this is a new card and should follow the add journey."""
        #
        #     for scheme_account in matching_user_scheme_accounts:
        #         print(scheme_account.id)
        #
        #     if len(matching_user_scheme_accounts) > 0:
        #         print("THIS IS AN EXISTING ACCOUNT ALREADY IN THIS WALLET")
        #
        #         # Responds with details of existing scheme account(s)
        #         details = []
        #         for scheme_account in matching_cred_scheme_accounts:
        #             details.append({"id": scheme_account, "loyalty_plan": plan})
        #
        #         resp_body = [
        #             {
        #                 "loyalty_card": details,
        #                 "message": "Existing loyalty card(s) already in this user's wallet",
        #             }
        #         ]
        #         resp_status = falcon.HTTP_200
        #
        #     else:
        #         print("ADDING USER TO THE MATCHING SCHEME ACCOUNT(S)")
        #
        #         # Adds link(s) between current user and existing scheme account(s)
        #         links_to_insert = []
        #         for scheme_account in matching_cred_scheme_accounts:
        #             links_to_insert.append(
        #                 SchemeAccountUserAssociation(scheme_account_id=scheme_account, user_id=user_id)
        #             )
        #
        #         self.session.bulk_save_objects(links_to_insert)
        #         self.session.commit()
        #
        #         # Responds with details of existing scheme account(s)
        #         details = []
        #         for scheme_account in matching_cred_scheme_accounts:
        #             details.append({"id": scheme_account, "loyalty_plan": plan})
        #
        #         resp_body = {
        #             "loyalty_card": details,
        #             "message": "Linked user to existing loyalty card(s).",
        #         }
        #         resp_status = falcon.HTTP_200
        #
        # # --------------IF matching credentials are NOT found:--------------
        #
        # else:
        #     print("ADDING NEW SCHEME ACCOUNT AND LINKING TO THIS WALLET")
        #
        #     # Fetches values for card_number, barcode and main_answer
        #     card_number = None
        #     barcode = None
        #     main_answer = None
        #
        #     for cred in add_and_auth_creds:
        #         linked_question = all_scheme_questions[cred["credential_slug"]]
        #         if linked_question["type"] == "card_number":
        #             card_number = cred["value"]
        #         elif linked_question["type"] == "barcode":
        #             barcode = cred["value"]
        #
        #         if linked_question["manual_question"] is True:
        #             main_answer = cred["value"]
        #
        #     if not main_answer and not card_number and not barcode:
        #         print("ERROR: No barcode, card_number or other main_answer credential provided!")
        #
        #     print("card_number is " + str(card_number))
        #     print("barcode " + str(barcode))
        #     print("main_answer is " + str(main_answer))
        #
        #     # Creates new SchemeAccount in PENDING
        #     statement_insert_scheme_account = insert(SchemeAccount).values(
        #         status=0,
        #         order=1,
        #         created=datetime.now(),
        #         updated=datetime.now(),
        #         card_number=card_number or "",
        #         barcode=barcode or "",
        #         main_answer=main_answer or "",
        #         scheme_id=plan,
        #         is_deleted=False,
        #     )
        #
        #     new_row = self.session.execute(statement_insert_scheme_account)
        #
        #     new_scheme_account_id = new_row.inserted_primary_key[0]
        #
        #     self.session.commit()
        #
        #     # Creates link between SchemeAccount and User
        #     statement_insert_scheme_account_user_link = insert(SchemeAccountUserAssociation).values(
        #         scheme_account_id=new_scheme_account_id, user_id=user_id
        #     )
        #
        #     self.session.execute(statement_insert_scheme_account_user_link)
        #     self.session.commit()
        #
        #     # Adds credential answers into SchemeAccountCredentialAnswer table
        #     answers_to_add = []
        #     for cred in add_and_auth_creds:
        #         answers_to_add.append(
        #             SchemeAccountCredentialAnswer(
        #                 scheme_account_id=new_scheme_account_id,
        #                 question_id=all_scheme_questions[cred["credential_slug"]]["question_id"],
        #                 answer=cred["value"],
        #             )
        #         )
        #
        #     self.session.bulk_save_objects(answers_to_add)
        #     self.session.commit()
        #
        #     # Sends new SchemeAccount id to Hermes for PLL and Midas auth.
        #     print("SENDING SCHEME ACCOUNT INFORMATION TO HERMES FOR PLL AND MIDAS AUTH")
        #
        #     send_message_to_hermes("add_loyalty_card_journey", {"scheme_account_id": new_scheme_account_id})
        #
        #     # Responds with 201
        #     resp_body = {
        #         "id": new_scheme_account_id,
        #         "loyalty_plan": plan,
        #         "message": "Loyalty Card created in wallet.",
        #     }
        #     resp_status = falcon.HTTP_201
        #
        # resp.media = resp_body
        # resp.status = resp_status

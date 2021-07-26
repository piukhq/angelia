import falcon

from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from sqlalchemy import join, select

from app.handlers.base import BaseHandler
from app.report import api_logger
from app.hermes.models import (
    Channel,
    Scheme,
    SchemeAccount,
    SchemeAccountCredentialAnswer,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeCredentialQuestion,
 )
from app.messaging.sender import send_message_to_hermes


@dataclass
class LoyaltyCardHandler(BaseHandler):
    loyalty_plan: int
    account: dict
    add_fields: list = None
    auth_fields: list = None
    register_fields: list = None
    card_number: str = None
    barcode: str = None
    main_answer: str = None
    plan_credential_questions: dict = None

    def __post_init__(self):
        self.retrieve_cred_fields()
        pass

    def store_card(self):
        api_logger.info("Starting Loyalty Card Store journey")
        # Check if wallet already contains a loyalty card linked to plan ID
        credential_questions = self.get_plan_credential_questions()
        self.check_provided_credentials(credential_questions,
                                        credential_answers=self.add_fields)

    def check_provided_credentials(self, credential_questions, credential_answers,
                                   auth=False,
                                   register=False,
                                   enrol=False
                                   ):
        # Validates credential fields
        # Also adds to required_scheme_question if it's an add field (by default) or auth, enrol or register fields
        # (as flagged in function call)
        required_scheme_questions = []
        self.plan_credential_questions = {}

        for question in credential_questions:

            self.plan_credential_questions[question.SchemeCredentialQuestion.label] = {
                "question_id": question.SchemeCredentialQuestion.id,
                "type": question.SchemeCredentialQuestion.type,
                "manual_question": question.SchemeCredentialQuestion.manual_question,
            }

            label = question.SchemeCredentialQuestion.label
            if question.SchemeCredentialQuestion.add_field is True and label not in required_scheme_questions:
                required_scheme_questions.append(label)
            if auth:
                if question.SchemeCredentialQuestion.auth_field is True and label not in required_scheme_questions:
                    required_scheme_questions.append(label)
            if register:
                if question.SchemeCredentialQuestion.register_field is True and label not in required_scheme_questions:
                    required_scheme_questions.append(label)
            if enrol:
                if question.SchemeCredentialQuestion.enrol_field is True and label not in required_scheme_questions:
                    required_scheme_questions.append(label)

        # Checks provided credential slugs against possible credential question slugs.
        # If this is a required field (auth or add), then this is removed from list of required fields
        # and 'ticked off'.
        # Also assigns card_number, barcode and main_answer values if applicable
        for cred in credential_answers:
            if cred["credential_slug"] not in list(self.plan_credential_questions.keys()):
                raise falcon.HTTPBadRequest("Invalid credential slug(s) provided")
            else:
                linked_question = self.plan_credential_questions[cred['credential_slug']]
                if linked_question['type'] == 'card_number':
                    self.card_number = cred['value']
                if linked_question['type'] == 'barcode':
                    self.barcode = cred['value']
                if linked_question['manual_question'] is True:
                    self.main_answer = cred['value']
                if cred["credential_slug"] in required_scheme_questions:
                    required_scheme_questions.remove(cred["credential_slug"])

        # If there are remaining auth or add fields (i.e. not all add/auth answers have been provided), ERROR.
        if required_scheme_questions:
            raise falcon.HTTPBadRequest("Not all required credentials have been provided")

    # If not, create new loyalty account with this information
    # and add cred answers to db
    # If so, return details of this loyalty account. (+ update creds?)
    # Send to Hermes for follow-up

    def get_plan_credential_questions(self):

        credential_questions = (
            self.db_session.query(SchemeCredentialQuestion)
            .join(Scheme)
            .join(SchemeChannelAssociation)
            .join(Channel)
            .filter(SchemeCredentialQuestion.scheme_id == self.loyalty_plan)
            .filter(Channel.bundle_id == self.channel_id)
            .filter(SchemeChannelAssociation.status == 0))

        return credential_questions

    def create_new_loyalty_card(self, credential_answers):
        loyalty_card = SchemeAccount(
            status=0,
            order=1,
            created=datetime.now(),
            updated=datetime.now(),
            card_number=self.card_number or "",
            barcode=self.barcode or "",
            main_answer=self.main_answer or "",
            scheme_id=self.loyalty_plan,
            is_deleted=False,
        )

        self.db_session.add(loyalty_card)
        self.db_session.flush()

        answers_to_add = []
        for cred in credential_answers:
            answers_to_add.append(
                SchemeAccountCredentialAnswer(
                    scheme_account_id=loyalty_card.id,
                    question_id=self.plan_credential_questions[cred["credential_slug"]]["question_id"],
                    answer=cred["value"],
                )
            )

        self.db_session.bulk_save_objects(answers_to_add)
        self.db_session.commit()

    def retrieve_cred_fields(self):
        try:
            self.add_fields = self.account.get('add_fields', [])
            self.auth_fields = self.account.get('authorise_fields', [])
            self.register_fields = self.account.get('register_fields', [])
        except KeyError:
            #error
            pass

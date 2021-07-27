import falcon

from dataclasses import dataclass
from datetime import datetime

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
    journey: str
    add_fields: list = None
    auth_fields: list = None
    register_fields: list = None
    card_number: str = None
    barcode: str = None
    main_answer: str = None
    id: int = None
    plan_credential_questions: dict = None
    all_answers: list = None
    cred_types: list = None

    def process_card(self):
        api_logger.info(f"Starting Loyalty Card {self.journey} journey")

        self.retrieve_cred_fields_from_req()
        self.set_journey()

        credential_questions = self.get_plan_credential_questions()
        self.check_provided_credentials(credential_questions)

        created = self.return_existing_or_create()

        response = {"id": self.id,
                    "loyalty_plan": self.loyalty_plan}

        return response, created

    def retrieve_cred_fields_from_req(self):
        try:
            self.add_fields = self.account.get('add_fields', [])
            self.auth_fields = self.account.get('authorise_fields', [])
            self.register_fields = self.account.get('register_fields', [])
        except KeyError:
            api_logger.error('KeyError when processing cred fields')
            raise falcon.HTTPInternalServerError('An Internal Server Error Occurred')
            pass

    def set_journey(self):
        # Sets accepted cred types and answers going forwards

        if self.journey == 'store':
            self.all_answers = self.add_fields
            self.cred_types = ['ADD']
        elif self.journey == 'add':
            self.all_answers = self.add_fields + self.auth_fields
            self.cred_types = ['ADD', 'AUTH']
        elif self.journey == 'register':
            self.all_answers = self.register_fields + self.auth_fields
            self.cred_types = ['REGISTER', 'AUTH']

    def get_plan_credential_questions(self):

        credential_questions = (
            self.db_session.query(SchemeCredentialQuestion)
            .join(Scheme)
            .join(SchemeChannelAssociation)
            .join(Channel)
            .filter(SchemeCredentialQuestion.scheme_id == self.loyalty_plan)
            .filter(Channel.bundle_id == self.channel_id)
            .filter(SchemeChannelAssociation.status == 0).all())

        return credential_questions

    def check_provided_credentials(self, credential_questions):
        required_scheme_questions = []
        self.plan_credential_questions = {}

        for question in credential_questions:

            if question.add_field or \
               ('AUTH' in self.cred_types and question.auth_field) or \
               ('REGISTER' in self.cred_types and question.register_field) or \
               ('ENROL' in self.cred_types and question.enrol_field):

                self.plan_credential_questions[question.label] = {
                    "question_id": question.id,
                    "type": question.type,
                    "manual_question": question.manual_question,
                }
                required_scheme_questions.append(question.label)

        # Checks provided credential question slugs against possible credential question slugs.
        # If this is a required field (auth or add), then this is removed from list of required fields
        # and 'ticked off'.
        # Also assigns card_number, barcode and main_answer values if available
        for cred in self.all_answers:
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
                required_scheme_questions.remove(cred["credential_slug"])

        # If there are remaining auth or add fields (i.e. not all add/auth answers have been provided), ERROR.
        if required_scheme_questions:
            raise falcon.HTTPBadRequest('Not all required credentials have been provided')

    def return_existing_or_create(self):
        card_number_question_id = None
        created = False

        for key, value in self.plan_credential_questions.items():
            if value['type'] == 'card_number':
                card_number_question_id = value['question_id']
        if card_number_question_id is None:
            api_logger.error(f'Cannot find card_number credential question for loyalty plan {self.loyalty_plan}')
            raise falcon.HTTPInternalServerError('An Internal Error Occurred')

        existing_objects = (
            self.db_session.query(SchemeAccount, SchemeAccountUserAssociation)
                .join(SchemeAccountCredentialAnswer)
                .join(SchemeAccountUserAssociation)
                .filter(SchemeAccountCredentialAnswer.answer == self.card_number)
                .filter(SchemeAccountCredentialAnswer.question_id == card_number_question_id)
                .filter(SchemeAccount.scheme_id == self.loyalty_plan)
                .filter(SchemeAccount.is_deleted == 'false')
                .all())

        existing_scheme_account_ids = []
        existing_user_ids = []

        for item in existing_objects:
            existing_user_ids.append(item.SchemeAccountUserAssociation.user_id)
            existing_scheme_account_ids.append(item.SchemeAccount.id)

        number_of_existing_accounts = len(set(existing_scheme_account_ids))

        if number_of_existing_accounts > 1:
            api_logger.error(f'Multiple Loyalty Cards found with matching information: {existing_scheme_account_ids}')
            raise falcon.HTTPInternalServerError('An Internal Error Occurred')
        elif number_of_existing_accounts == 0:
            self.create_new_loyalty_card()
            created = True

        else:
            self.id = existing_scheme_account_ids[0]
            api_logger.info(f'Existing loyalty card found: {self.id}')

            if self.user_id not in existing_user_ids:
                self.link_account_to_user()

        api_logger.info(f'Sending to Hermes for processing')
        # Send to Hermes for auto-linking etc.

        return created

    def create_new_loyalty_card(self):
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

        self.id = loyalty_card.id

        answers_to_add = []
        for cred in self.all_answers:
            answers_to_add.append(
                SchemeAccountCredentialAnswer(
                    scheme_account_id=self.id,
                    question_id=self.plan_credential_questions[cred["credential_slug"]]["question_id"],
                    answer=cred["value"],
                )
            )

        self.db_session.bulk_save_objects(answers_to_add)
        self.db_session.commit()

        api_logger.info(f'Created Loyalty Card {self.id} and associated cred answers')

        self.link_account_to_user()

    def link_account_to_user(self):
        api_logger.info(f'Linking Loyalty Card {self.id} to User Account {self.user_id}')
        user_association_object = SchemeAccountUserAssociation(scheme_account_id=self.id,
                                                               user_id=self.user_id)

        self.db_session.add(user_association_object)
        self.db_session.commit()

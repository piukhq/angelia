import falcon
import re
import sre_constants

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

ADD = 'ADD'
AUTHORISE = 'AUTH'
ADD_AND_AUTHORISE = 'ADD_AND_AUTH'
JOIN = 'JOIN'
REGISTER = 'REGISTER'

ADD_FIELD = 'add_field'
AUTH_FIELD = 'auth_field'
JOIN_FIELD = 'join_field'
REGISTER_FIELD = 'register_field'

CARD_NUMBER = 'card_number'
BARCODE = 'barcode'


@dataclass
class LoyaltyCardHandler(BaseHandler):
    """
    Handles all Loyalty Card journeys including Add, Auth, Add_and_auth, join and register.

    For clarity:
        -using QUESTION when referring to only the question or credentialquestions table (i.e. receiver)
        -using ANSWER when referring to only the information given in the request (i.e. supplier)
        -using CREDENTIAL for a valid combination of the two in context

        - credential TYPE is the db alias for a credential (e.g. card_number, barcode)
        - credential CLASS is the field type of a credential (e.g. add_field, enrol_field etc.)

    Leaving self.journey in for now, but this may turn out to be redundant.
    """

    loyalty_plan_id: int
    all_answer_fields: dict
    journey: str
    loyalty_plan_object: Scheme = None
    add_fields: list = None
    auth_fields: list = None
    register_fields: list = None
    valid_credentials: dict = None
    key_credential: dict = None

    id: int = None

    cred_types: list = None

    def add_card(self):
        api_logger.info(f"Starting Loyalty Card '{self.journey}' journey")

        credential_questions = self.retrieve_plan_questions_and_answer_fields()

        self.validate_all_credentials(credential_questions)

        created = self.return_existing_or_create()

        response = {"id": self.id,
                    "loyalty_plan": self.loyalty_plan_id}

        return response, created

    def retrieve_plan_questions_and_answer_fields(self):
        try:
            self.add_fields = self.all_answer_fields.get('add_fields', [])
            self.auth_fields = self.all_answer_fields.get('authorise_fields', [])
            self.register_fields = self.all_answer_fields.get('register_fields', [])

        except KeyError:
            api_logger.error('KeyError when processing answer fields')
            raise falcon.HTTPInternalServerError('An Internal Server Error Occurred')

        all_credential_questions = (
            self.db_session.query(SchemeCredentialQuestion, Scheme)
                .join(Scheme)
                .join(SchemeChannelAssociation)
                .join(Channel)
                .filter(SchemeCredentialQuestion.scheme_id == self.loyalty_plan_id)
                .filter(Channel.bundle_id == self.channel_id)
                .filter(SchemeChannelAssociation.status == 0).all())

        if len(all_credential_questions) < 1:
            api_logger.error('Loyalty plan does not exist, or no credential questions found')
            raise falcon.HTTPBadRequest('This loyalty plan is not available.')

        # todo: do we need separate errors for:
        #  loyalty plan not available to this channel (400/401?)
        #  loyalty plan does not exist (400/404?),
        #  loyalty plan exists but no questions (500)?

        # Store scheme object for later as will be needed for card_number/barcode regex on create
        self.loyalty_plan_object = all_credential_questions[0][1]

        return all_credential_questions

    def validate_all_credentials(self, all_credential_questions):
        """Cross-checks available plan questions with provided answers.
        Then populates a final list of validated credentials."""

        self.valid_credentials = {}

        # Validates credentials per credential class.
        # No need to relate this to with journey type - this is done in request validation.
        if self.add_fields:
            self.validate_credentials_by_class(all_credential_questions, self.add_fields, ADD_FIELD)
        if self.auth_fields:
            self.validate_credentials_by_class(all_credential_questions, self.auth_fields, AUTH_FIELD, require_all=True)
        if self.register_fields:
            self.validate_credentials_by_class(all_credential_questions, self.register_fields, REGISTER_FIELD, require_all=True)

        # Checks that at least one manual question, scan question or one question link has been given.
        for key, value in self.valid_credentials.items():
            if value['key_credential']:
                self.key_credential = value

        if not self.key_credential:
            api_logger.error('No main question (manual_question, scan_question, one_question_link found in given creds')
            raise falcon.HTTPBadRequest('At least one manual question, scan question or one question link must be '
                                        'provided')

    def validate_credentials_by_class(self, credential_questions, answer_set, credential_class, require_all=False):
        """
        Checks that for all answers matching a given credential class (e.g. 'auth_fields'), a corresponding scheme
        question exists. If require_all is set to True, then all available credential questions of this class must
        have a corresponding answer.
        """

        required_questions = []

        if require_all:
            for question, scheme in credential_questions:
                if getattr(question, credential_class):
                    required_questions.append(question.label)

        for answer in answer_set:
            answer_found = False
            for question, scheme in credential_questions:
                if answer['credential_slug'] == question.label and getattr(question, credential_class):

                    # Checks if this cred is the the 'key credential' which will effectively act as the pk for the
                    # existing account search later on. There should only be one (this is checked later)
                    key_credential = any([
                        getattr(question, 'manual_question'),
                        getattr(question, 'scan_question'),
                        getattr(question, 'one_question_link')
                    ])

                    # For clarity:
                    # using QUESTION when referring to only the question or credentialquestions table (i.e. receiver)
                    # using ANSWER when referring to only the information given in the request (i.e. supplier)
                    # using CREDENTIAL where there is an intersection of the two
                    self.valid_credentials[question.label] = {
                        "credential_question_id": question.id,
                        "credential_type": question.type,
                        "credential_class": credential_class,
                        "key_credential": key_credential,
                        "credential_answer": answer['value'],
                    }
                    answer_found = True
                    try:
                        required_questions.remove(question.label)
                    except ValueError:
                        pass
                    break
            if not answer_found:
                api_logger.error(f'Credential {answer["credential_slug"]} not found for this scheme')
                raise falcon.HTTPBadRequest('Invalid credentials provided')

        if required_questions and require_all:
            api_logger.error(f'Missing required {credential_class} credential(s) {required_questions}')
            raise falcon.HTTPBadRequest('Missing required credentials for this scheme')

    def return_existing_or_create(self):
        created = False

        if self.key_credential['credential_type'] in [CARD_NUMBER, BARCODE]:
            key_credential_field = self.key_credential['credential_type']
        else:
            key_credential_field = 'main_answer'

        existing_objects = (
            self.db_session.query(SchemeAccount, SchemeAccountUserAssociation, Scheme)
                .join(SchemeAccountCredentialAnswer)
                .join(SchemeAccountUserAssociation)
                .join(Scheme)
                .filter(getattr(SchemeAccount, key_credential_field) == self.key_credential['credential_answer'])
                .filter(SchemeAccount.scheme_id == self.loyalty_plan_id)
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

    def get_card_number_and_barcode(self):
        """ Search valid_credentials for card_number or barcode types. If either is missing, then try to generate one
        from the other using regex patterns from the Scheme, and then pass both back to populate the scheme account
        record."""

        barcode, card_number = None, None
        loyalty_plan = self.loyalty_plan_object

        for key, cred in self.valid_credentials.items():
            if cred['credential_type'] == CARD_NUMBER:
                card_number = cred['credential_answer']
            elif cred['credential_type'] == BARCODE:
                barcode = cred['credential_answer']

        if barcode and not card_number and loyalty_plan.barcode_regex and loyalty_plan.card_number_prefix:
            # convert barcode to card_number using regex
            try:
                regex = re.search(loyalty_plan.barcode_regex, barcode)
                card_number = loyalty_plan.card_number_prefix + regex.group(1)
            except (sre_constants.error, ValueError) as e:
                api_logger("Failed to convert barcode to card_number")
        elif barcode and not card_number:
            card_number = barcode

        if card_number and not barcode and loyalty_plan.card_number_regex and loyalty_plan.barcode_prefix:
            try:
                regex = re.search(loyalty_plan.card_number_regex, card_number)
                barcode = loyalty_plan.barcode_prefix + regex.group(1)
            except (sre_constants.error, ValueError) as e:
                api_logger("Failed to convert card_number to barcode")
        elif card_number and not barcode:
            barcode = card_number

        return card_number, barcode

    def create_new_loyalty_card(self):

        card_number, barcode = self.get_card_number_and_barcode()

        loyalty_card = SchemeAccount(
            status=0,
            order=1,
            created=datetime.now(),
            updated=datetime.now(),
            card_number=card_number or "",
            barcode=barcode or "",
            main_answer=self.key_credential['credential_answer'],
            scheme_id=self.loyalty_plan_id,
            is_deleted=False,
        )

        self.db_session.add(loyalty_card)
        self.db_session.flush()

        self.id = loyalty_card.id

        answers_to_add = []
        for key, cred in self.valid_credentials.items():
            answers_to_add.append(
                SchemeAccountCredentialAnswer(
                    scheme_account_id=self.id,
                    question_id=cred["credential_question_id"],
                    answer=cred["credential_answer"],
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

# todo: case-sensitive credential answers (do we make a list of these, as in ubiquity, or do we have some common area?)

# todo: validation - regex/length etc.

# todo: encryption/decryption of sensitive data

# todo: consent data

# todo: handle escaped unicode

# todo: metrics

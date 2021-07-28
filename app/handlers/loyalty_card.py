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

ADD = 'ADD'
AUTHORISE = 'AUTH'
ADD_AND_AUTHORISE = 'ADD_AND_AUTH'
JOIN = 'JOIN'
REGISTER = 'REGISTER'

credential_types = {
    'ADD': ['add_field'],
    'AUTH': ['add_field', 'auth_field'],
    'JOIN': ['add_field', 'enrol_field'],
    'REGISTER': ['add_field', 'register_field']
}


@dataclass
class LoyaltyCardHandler(BaseHandler):
    loyalty_plan: int
    account: dict
    journey: str
    add_fields: list = None
    auth_fields: list = None
    register_fields: list = None
    main_answer: str = None
    loyalty_card_object: SchemeAccount = None
    loyalty_plan_object: Scheme = None
    id: int = None
    valid_credentials: dict = None
    all_answers: list = None
    cred_types: list = None

    def process_card(self):
        api_logger.info(f"Starting Loyalty Card '{self.journey}' journey")

        self.retrieve_cred_fields_from_req()

        self.check_provided_credentials()

        created = self.return_existing_or_create()

        response = {"id": self.id,
                    "loyalty_plan": self.loyalty_plan}

        return response, created

    def retrieve_cred_fields_from_req(self):
        try:
            self.add_fields = self.account.get('add_fields', [])
            self.auth_fields = self.account.get('authorise_fields', [])
            self.register_fields = self.account.get('register_fields', [])

            self.all_answers = self.add_fields + self.auth_fields + self.register_fields
        except KeyError:
            api_logger.error('KeyError when processing cred fields')
            raise falcon.HTTPInternalServerError('An Internal Server Error Occurred')
            pass

    def check_provided_credentials(self):

        # Check that given credential is A. A valid credential in the list, B. An [ADD] credential, then populate with
        # question_id, question_type, and answer

        credential_questions = (
            self.db_session.query(SchemeCredentialQuestion)
                .join(Scheme)
                .join(SchemeChannelAssociation)
                .join(Channel)
                .filter(SchemeCredentialQuestion.scheme_id == self.loyalty_plan)
                .filter(Channel.bundle_id == self.channel_id)
                .filter(SchemeChannelAssociation.status == 0).all())

        self.valid_credentials = {}
        for answer in self.all_answers:
            answer_found = False
            for question in credential_questions:
                if answer['credential_slug'] == question.label and \
                        any([getattr(question, cred_type) for cred_type in credential_types[self.journey]]):
                    self.valid_credentials[question.label] = {
                        "question_id": question.id,
                        "type": question.type,
                        "manual_question": question.manual_question,
                        "value": answer['value']
                    }
                    answer_found = True
                    break
            if not answer_found:
                raise falcon.HTTPBadRequest('Invalid credentials provided')

    def return_existing_or_create(self):
        card_number_question_id = None
        created = False

        for key, value in self.valid_credentials.items():
            if value['type'] == 'card_number':
                card_number_question_id = value['question_id']
        if card_number_question_id is None:
            api_logger.error(f'Cannot find card_number credential question for loyalty plan {self.loyalty_plan}')
            raise falcon.HTTPInternalServerError('An Internal Error Occurred')

        # Use the first available credential as the main credential (there should only be 1 anyway for
        # add-only journeys.)
        # If there are multiple creds, and one of these is marked as the main question, then use this instead.
        self.main_answer = self.valid_credentials[list(self.valid_credentials.keys())[0]]['value']

        for key, value in self.valid_credentials.items():
            if value['manual_question']:
                self.main_answer = self.valid_credentials[key]['value']

        existing_objects = (
            self.db_session.query(SchemeAccount, SchemeAccountUserAssociation, Scheme)
                .join(SchemeAccountCredentialAnswer)
                .join(SchemeAccountUserAssociation)
                .join(Scheme)
                .filter(SchemeAccount.main_answer == self.main_answer)
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

    def get_card_number_and_barcode(self):
        # todo: In order to properly generate these, we will need to check the Scheme for barcode and card_number regex
        #  information. This could be done in a separate query, or else we could return this in the original cred
        #  questions query, which is probably better overall.

        # Search valid_credentials for card_number or barcode types. If either is missing, then try to generate one from
        # the other using regex patterns from the Scheme, and then pass both back to populate the scheme account record.

        barcode, card_number = None, None

        for key, value in self.valid_credentials.items():
            if value['type'] == 'card_number':
                card_number= value['value']
            elif value['type'] == 'barcode':
                barcode = value['value']

        if barcode and not card_number:
            # convert barcode to card_number using regex
            pass

        if card_number and not barcode:
            # convert card_number to barcode using regex
            pass

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
            main_answer=self.main_answer,
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
                    question_id=self.valid_credentials[cred["credential_slug"]]["question_id"],
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

# todo: case-sensitive credential answers (do we make a list of these, as in ubiquity?)

# todo: handling manual question/main answer. There are some cases where this question is actually an auth field. Do
#  we really want a user to need to include an auth field as an add field? In Ubiquity, the answer_type comes from the
#  serializer context, which determines the type of answer required (e.g. card_number, barcode) etc. HN does have a
#  card_number, but it's manual question is email, which is an auth field (and so theoretically shouldn't be passed in
#  with this request for a store card)

# todo: validation

# todo: prevent user from adding redundant cred field types in request.

"""
1. We should only accept one add field
2. That add field should be checked as being a valid add field against the loyalty plan
3. If the add field is type 'card_number' or 'barcode', we should generate the opposite using regex from the 
loyalty plan
4. We should use the value of that add field as the 'search' key for a valid scheme account, in combination with the 
loyalty plan. (if card_number or barcode then search both for matching value)

"""

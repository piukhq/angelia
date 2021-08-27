import re
import sre_constants
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

import falcon
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy import select
from app.api.exceptions import ValidationError
from app.api.helpers.vault import AESKeyNames
from app.handlers.base import BaseHandler
from app.hermes.models import (
    Channel,
    Scheme,
    SchemeAccount,
    SchemeAccountCredentialAnswer,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeCredentialQuestion,
)
from app.lib.credentials import CASE_SENSITIVE_CREDENTIALS, ENCRYPTED_CREDENTIALS
from app.lib.encryption import AESCipher
from app.messaging.sender import send_message_to_hermes
from app.report import api_logger

ADD = "ADD"
AUTHORISE = "AUTH"
ADD_AND_AUTHORISE = "ADD_AND_AUTH"
JOIN = "JOIN"
REGISTER = "REGISTER"


class CredentialClass(str, Enum):
    ADD_FIELD = "add_field"
    AUTH_FIELD = "auth_field"
    JOIN_FIELD = "enrol_field"  # API naming convention does not yet match db level field name
    REGISTER_FIELD = "register_field"


class QuestionType(str, Enum):
    CARD_NUMBER = "card_number"
    BARCODE = "barcode"


@dataclass
class LoyaltyCardHandler(BaseHandler):
    """
    Handles all Loyalty Card journeys including Add, Auth, Add_and_auth, join and register.

    For clarity:
        -using QUESTION when referring to only the question or credential_questions table (i.e. receiver)
        -using ANSWER when referring to only the information given in the request (i.e. supplier)
        -using CREDENTIAL for a valid combination of the two in context

        - credential TYPE is the db alias for a credential (e.g. card_number, barcode)
        - credential CLASS is the field type of a credential (e.g. add_field, enrol_field etc.)

    Leaving self.journey in for now, but this may turn out to be redundant.
    """

    loyalty_plan_id: int
    all_answer_fields: dict
    journey: str
    loyalty_plan: Scheme = None
    add_fields: list = None
    auth_fields: list = None
    register_fields: list = None
    join_fields: list = None
    valid_credentials: dict = None
    key_credential: dict = None

    card_id: int = None
    plan_credential_questions: dict[CredentialClass, dict[QuestionType, SchemeCredentialQuestion]] = None

    cred_types: list = None

    @staticmethod
    def _format_questions(
            all_credential_questions: Iterable[SchemeCredentialQuestion],
    ) -> dict[CredentialClass, dict[QuestionType, SchemeCredentialQuestion]]:
        """Restructures credential questions for easier access of questions by CredentialClass and QuestionType"""

        formatted_questions = {cred_class.value: {} for cred_class in CredentialClass}
        for question in all_credential_questions:
            for cred_class in CredentialClass:
                if getattr(question, cred_class):
                    formatted_questions[cred_class][question.type] = question

        return formatted_questions

    def _add_card(self):
        api_logger.info(f"Starting Loyalty Card '{self.journey}' journey")

        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials()
        created = self.link_to_user_existing_or_create()
        return created

    def add_card_to_wallet(self):
        # Note ADD only is for store cards - Hermes does not need to link these so no
        # need to call hermes.
        created = self._add_card()
        return created

    def add_auth_card(self) -> bool:
        created = self._add_card()
        api_logger.info("Sending to Hermes for onward journey")
        hermes_message = self._hermes_messaging_data(created=created)
        hermes_message["auth_fields"] = deepcopy(self.auth_fields)
        send_message_to_hermes("loyalty_card_add_and_auth", hermes_message)
        return created

    def retrieve_plan_questions_and_answer_fields(self) -> None:
        try:
            self.add_fields = self.all_answer_fields.get("add_fields", [])
            self.auth_fields = self.all_answer_fields.get("authorise_fields", [])
            self.register_fields = self.all_answer_fields.get("register_fields", [])
            self.join_fields = self.all_answer_fields.get("enrol_fields", [])

        except KeyError:
            api_logger.exception("KeyError when processing answer fields")
            # Todo: this should probably be a validation error. It is unlikely to be reached if the validator is correct
            #  but in the case that it does it would be due to the client providing invalid data.
            raise falcon.HTTPInternalServerError

        query = select(SchemeCredentialQuestion, Scheme) \
            .join(Scheme) \
            .join(SchemeChannelAssociation) \
            .join(Channel) \
            .filter(SchemeCredentialQuestion.scheme_id == self.loyalty_plan_id) \
            .filter(Channel.bundle_id == self.channel_id) \
            .filter(SchemeChannelAssociation.status == 0)

        try:
            all_credential_questions_and_plan = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        if len(all_credential_questions_and_plan) < 1:
            api_logger.error(
                "Loyalty plan does not exist, is not available for this channel, or no credential questions found"
            )
            raise ValidationError

        # Store scheme object for later as will be needed for card_number/barcode regex on create
        self.loyalty_plan = all_credential_questions_and_plan[0][1]

        all_questions = [question[0] for question in all_credential_questions_and_plan]
        self.plan_credential_questions = self._format_questions(all_questions)

    def validate_all_credentials(self) -> None:
        """Cross-checks available plan questions with provided answers.
        Then populates a final list of validated credentials."""

        self.valid_credentials = {}

        # Validates credentials per credential class.
        # No need to relate this to with journey type - this is done in request validation.
        if self.add_fields:
            self.validate_credentials_by_class(self.add_fields, CredentialClass.ADD_FIELD)
        if self.auth_fields:
            self.validate_credentials_by_class(self.auth_fields, CredentialClass.AUTH_FIELD, require_all=True)
        if self.register_fields:
            self.validate_credentials_by_class(self.register_fields, CredentialClass.REGISTER_FIELD, require_all=True)

        # Checks that at least one manual question, scan question or one question link has been given.
        for key, cred in self.valid_credentials.items():
            if cred["key_credential"]:
                self.key_credential = cred

        if not self.key_credential:
            err_msg = "At least one manual question, scan question or one question link must be provided."
            api_logger.error(err_msg)
            raise ValidationError

    @staticmethod
    def _process_case_sensitive_credentials(credential_slug: str, credential: str) -> str:
        return credential.lower() if credential_slug not in CASE_SENSITIVE_CREDENTIALS else credential

    def _check_answer_has_matching_question(self, answer: dict, credential_class: CredentialClass) -> None:
        try:
            question = self.plan_credential_questions[credential_class][answer["credential_slug"]]
            answer["value"] = self._process_case_sensitive_credentials(answer["credential_slug"], answer["value"])
            # Checks if this cred is the the 'key credential' which will effectively act as the pk for the
            # existing account search later on. There should only be one (this is checked later)
            key_credential = any(
                [
                    getattr(question, "manual_question"),
                    getattr(question, "scan_question"),
                    getattr(question, "one_question_link"),
                ]
            )

            self.valid_credentials[question.type] = {
                "credential_question_id": question.id,
                "credential_type": question.type,
                "credential_class": credential_class,
                "key_credential": key_credential,
                "credential_answer": answer["value"],
            }
        except KeyError:
            err_msg = f'Credential {answer["credential_slug"]} not found for this scheme'
            api_logger.error(err_msg)
            raise ValidationError

    def validate_credentials_by_class(
            self, answer_set: Iterable[dict], credential_class: CredentialClass, require_all: bool = False
    ) -> None:
        """
        Checks that for all answers matching a given credential class (e.g. 'auth_fields'), a corresponding scheme
        question exists. If require_all is set to True, then all available credential questions of this class must
        have a corresponding answer.
        """
        required_questions = {}
        if require_all:
            required_questions = self.plan_credential_questions[credential_class]

        for answer in answer_set:
            self._check_answer_has_matching_question(answer, credential_class)
            required_questions.pop(answer["credential_slug"], None)

        if required_questions and require_all:
            err_msg = f"Missing required {credential_class} credential(s) {required_questions}"
            api_logger.error(err_msg)
            raise ValidationError

    def link_to_user_existing_or_create(self) -> bool:
        created = False

        if self.key_credential["credential_type"] in [QuestionType.CARD_NUMBER, QuestionType.BARCODE]:
            key_credential_field = self.key_credential["credential_type"]
        else:
            key_credential_field = "main_answer"

        query = select(SchemeAccount, SchemeAccountUserAssociation, Scheme) \
            .join(SchemeAccountUserAssociation) \
            .join(Scheme) \
            .filter(getattr(SchemeAccount, key_credential_field) == self.key_credential["credential_answer"]) \
            .filter(SchemeAccount.scheme_id == self.loyalty_plan_id) \
            .filter(SchemeAccount.is_deleted.is_(False),)

        try:
            existing_objects = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database when linking user")
            raise falcon.HTTPInternalServerError

        existing_scheme_account_ids = []
        existing_user_ids = []

        for item in existing_objects:
            existing_user_ids.append(item.SchemeAccountUserAssociation.user_id)
            existing_scheme_account_ids.append(item.SchemeAccount.id)

        number_of_existing_accounts = len(set(existing_scheme_account_ids))

        if number_of_existing_accounts == 0:
            self.create_new_loyalty_card()
            created = True
        elif number_of_existing_accounts == 1:
            self.card_id = existing_scheme_account_ids[0]
            api_logger.info(f"Existing loyalty card found: {self.card_id}")

            if self.user_id not in existing_user_ids:
                # need to check that auth answers are identical if there are auth answers
                # also consider kash uodate
                self.link_account_to_user()
        else:
            api_logger.error(f"Multiple Loyalty Cards found with matching information: {existing_scheme_account_ids}")
            raise falcon.HTTPInternalServerError

        return created

    @staticmethod
    def _generate_card_number_from_barcode(loyalty_plan, barcode):
        try:
            regex_match = re.search(loyalty_plan.card_number_regex, barcode)
            if regex_match:
                return loyalty_plan.card_number_prefix + regex_match.group(1)
        except (sre_constants.error, ValueError):
            api_logger.warning("Failed to convert barcode to card_number")

    @staticmethod
    def _generate_barcode_from_card_number(loyalty_plan, card_number):
        try:
            regex_match = re.search(loyalty_plan.barcode_regex, card_number)
            if regex_match:
                return loyalty_plan.barcode_prefix + regex_match.group(1)
        except (sre_constants.error, ValueError):
            api_logger.warning("Failed to convert card_number to barcode")

    def _get_card_number_and_barcode(self):
        """Search valid_credentials for card_number or barcode types. If either is missing, and there is a regex
        pattern available to generate it, then generate and pass back."""

        barcode, card_number = None, None
        loyalty_plan: Scheme = self.loyalty_plan

        for key, cred in self.valid_credentials.items():
            if cred["credential_type"] == QuestionType.CARD_NUMBER:
                card_number = cred["credential_answer"]
            elif cred["credential_type"] == QuestionType.BARCODE:
                barcode = cred["credential_answer"]

        if barcode and not card_number and loyalty_plan.card_number_regex:
            card_number = self._generate_card_number_from_barcode(loyalty_plan, barcode)

        if card_number and not barcode and loyalty_plan.barcode_regex:
            barcode = self._generate_barcode_from_card_number(loyalty_plan, card_number)

        return card_number, barcode

    def create_new_loyalty_card(self):

        card_number, barcode = self._get_card_number_and_barcode()

        loyalty_card = SchemeAccount(
            status=0,
            order=1,
            created=datetime.now(),
            updated=datetime.now(),
            card_number=card_number or "",
            barcode=barcode or "",
            main_answer=self.key_credential["credential_answer"],
            scheme_id=self.loyalty_plan_id,
            is_deleted=False,
        )

        self.db_session.add(loyalty_card)
        self.db_session.flush()

        self.card_id = loyalty_card.id

        answers_to_add = []
        for key, cred in self.valid_credentials.items():
            if key in ENCRYPTED_CREDENTIALS:
                cred["credential_answer"] = (
                    AESCipher(AESKeyNames.AES_KEY).encrypt(cred["credential_answer"]).decode("utf-8")
                )

            answers_to_add.append(
                SchemeAccountCredentialAnswer(
                    scheme_account_id=self.card_id,
                    question_id=cred["credential_question_id"],
                    answer=cred["credential_answer"],
                )
            )

        self.db_session.bulk_save_objects(answers_to_add)

        try:
            # Does not commit until user is linked. This ensures atomicity if user linking fails due to missing or
            # invalid user_id(otherwise a loyalty card and associated creds would be committed without a link to the
            # user.)
            self.db_session.flush()
        except DatabaseError:
            api_logger.error("Failed to commit new loyalty plan and card credential answers.")
            raise falcon.HTTPInternalServerError

        api_logger.info(f"Created Loyalty Card {self.card_id} and associated cred answers")

        self.link_account_to_user()

    def link_account_to_user(self):
        # need to add in status for wallet only
        api_logger.info(f"Linking Loyalty Card {self.card_id} to User Account {self.user_id}")
        user_association_object = SchemeAccountUserAssociation(scheme_account_id=self.card_id, user_id=self.user_id)

        self.db_session.add(user_association_object)

        try:
            # Commits new loyalty card, cred answers and link to user all at once.
            self.db_session.commit()

        except IntegrityError:
            api_logger.error(
                f"Failed to link Loyalty Card {self.card_id} with User Account {self.user_id}: Integrity Error"
            )
            raise ValidationError
        except DatabaseError:
            api_logger.error(
                f"Failed to link Loyalty Card {self.card_id} with User Account {self.user_id}: Database Error"
            )
            raise falcon.HTTPInternalServerError

    def _hermes_messaging_data(self, created: bool) -> dict:
        return {
            "loyalty_card_id": self.card_id,
            "user_id": self.user_id,
            "channel": self.channel_id,
            "journey": self.journey,
            "auto_link": True,
            "created": created,
        }

# consent data - join and register only (marketing preferences/T&C) - park this for now

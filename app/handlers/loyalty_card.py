import re
import sre_constants
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional, Union

import falcon
from sqlalchemy import select, update
from sqlalchemy.engine import Row
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.api.exceptions import ResourceNotFoundError, ValidationError
from app.api.helpers.vault import AESKeyNames
from app.handlers.base import BaseHandler
from app.handlers.loyalty_plan import LoyaltyPlanChannelStatus
from app.hermes.models import (
    Channel,
    ClientApplication,
    Consent,
    Scheme,
    SchemeAccount,
    SchemeAccountCredentialAnswer,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeCredentialQuestion,
    ThirdPartyConsentLink,
)
from app.lib.credentials import CASE_SENSITIVE_CREDENTIALS, ENCRYPTED_CREDENTIALS, MERCHANT_IDENTIFIER
from app.lib.encryption import AESCipher
from app.lib.loyalty_card import LoyaltyCardStatus, OriginatingJourney
from app.messaging.sender import send_message_to_hermes
from app.report import api_logger

ADD = "ADD"
TRUSTED_ADD = "TRUSTED_ADD"
AUTHORISE = "AUTH"
ADD_AND_AUTHORISE = "ADD_AND_AUTH"
ADD_AND_REGISTER = "ADD_AND_REGISTER"
JOIN = "JOIN"
REGISTER = "REGISTER"
DELETE = "DELETE"


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
    Handles all Loyalty Card journeys.

    For clarity:
        -using QUESTION when referring to only the question or credential_questions table (i.e. receiver)
        -using ANSWER when referring to only the information given in the request (i.e. supplier)
        -using CREDENTIAL for a valid combination of the two in context

        - credential TYPE is the db alias for a credential (e.g. card_number, barcode)
        - credential CLASS is the field type of a credential (e.g. add_field, enrol_field etc.)


    """

    journey: str
    is_trusted_channel: bool = False
    all_answer_fields: dict = None
    loyalty_plan_id: int = None
    loyalty_plan: Scheme = None
    add_fields: list = None
    auth_fields: list = None
    register_fields: list = None
    join_fields: list = None
    merchant_fields: list = None
    valid_credentials: dict = None
    key_credential: dict = None
    all_consents: list = None
    link_to_user: Optional[SchemeAccountUserAssociation] = None
    card_id: int = None
    card: SchemeAccount = None
    plan_credential_questions: dict[CredentialClass, dict[QuestionType, SchemeCredentialQuestion]] = None
    plan_consent_questions: list[Consent] = None

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

            # Collect any additional merchant fields required for trusted channels.
            if getattr(question, "third_party_identifier"):
                formatted_questions["merchant_field"] = {}
                formatted_questions["merchant_field"][question.type] = question

        return formatted_questions

    def _get_key_credential_field(self) -> str:
        if self.key_credential and self.key_credential["credential_type"] in [
            QuestionType.CARD_NUMBER,
            QuestionType.BARCODE,
        ]:
            key_credential_field = self.key_credential["credential_type"]
        else:
            key_credential_field = "alt_main_answer"

        return key_credential_field

    def handle_add_only_card(self) -> bool:
        created = self.add_or_link_card()
        self.send_to_hermes_add_only()
        return created

    def handle_trusted_add_card(self) -> bool:
        # Adds card for a trusted channel. Assumes channel has already been authorised.
        api_logger.info(f"Starting Loyalty Card '{self.journey}' journey")
        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials(auth_require_all=False)
        self.validate_merchant_identifier()

        created = self.link_user_to_existing_or_create()
        self.send_to_hermes_trusted_add()
        return created

    def handle_trusted_update_card(self) -> bool:
        send_to_hermes_delete_and_add = False
        send_to_hermes_update = False

        # Keep a reference to the card_id in case the update results in a new account, which will override self.card_id
        # This will then be needed to send hermes a card deletion request
        old_card_id = self.card_id

        self.fetch_and_check_existing_card_links()
        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials(auth_require_all=False)
        self.validate_and_refactor_consents()

        if (
            not self.key_credential
            or getattr(self.card, self._get_key_credential_field(), None) == self.key_credential["credential_answer"]
        ):
            existing_creds, matching_creds = self.check_auth_credentials_against_existing()
            # Check if given merchant identifier matches any existing merchant identifier for this account.
            # All users linked to the account should have the same merchant_id so we raise an error if the new
            # value doesn't match
            existing_merchant_identifier = self.validate_merchant_identifier()

            # We will only NOT send to hermes if this user's credentials match what they already have
            if not (existing_creds and matching_creds) or (self.merchant_fields and not existing_merchant_identifier):
                send_to_hermes_update = True

        else:
            self.journey = TRUSTED_ADD
            existing_objects = self._get_existing_objects_by_key_cred()
            send_to_hermes_delete_and_add = self._route_journeys(existing_objects)

        if send_to_hermes_delete_and_add:
            hermes_message = self._hermes_messaging_data()
            hermes_message["loyalty_card_id"] = old_card_id
            hermes_message["journey"] = DELETE
            send_message_to_hermes("delete_loyalty_card", hermes_message)

            # generate request event
            self._dispatch_request_event()
            self.send_to_hermes_trusted_add()
        elif send_to_hermes_update:
            self._dispatch_request_event()
            self.send_to_hermes_trusted_add()

        return send_to_hermes_delete_and_add or send_to_hermes_update

    def handle_add_auth_card(self) -> bool:
        send_to_hermes = self.add_or_link_card(validate_consents=True)
        self._dispatch_request_event()
        if send_to_hermes:
            self.send_to_hermes_add_auth()
        return send_to_hermes

    def handle_add_register_card(self) -> bool:
        send_to_hermes = self.add_or_link_card(validate_consents=True)
        if send_to_hermes:
            api_logger.info("Sending to Hermes for onward journey")
            hermes_message = self._hermes_messaging_data()
            hermes_message["add_fields"] = deepcopy(self.add_fields)
            hermes_message["register_fields"] = deepcopy(self.register_fields)
            hermes_message["consents"] = deepcopy(self.all_consents)
            send_message_to_hermes("loyalty_card_add_and_register", hermes_message)
        return send_to_hermes

    def handle_authorise_card(self) -> bool:
        send_to_hermes_add_auth = False
        send_to_hermes_auth = False

        # Keep a reference to the card_id in case the update results in a new account, which will override self.card_id
        # This will then be needed to send hermes a card deletion request
        old_card_id = self.card_id

        self.fetch_and_check_existing_card_links()
        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials()
        self.validate_and_refactor_consents()

        if (
            not self.key_credential
            or getattr(self.card, self._get_key_credential_field(), None) == self.key_credential["credential_answer"]
        ):
            existing_creds, matching_creds = self.check_auth_credentials_against_existing()
            send_to_hermes_auth = not (existing_creds and matching_creds)
            # We will only NOT send to hermes if this user's credentials match what they already have
        else:
            self.journey = ADD_AND_AUTHORISE
            existing_objects = self._get_existing_objects_by_key_cred()
            send_to_hermes_add_auth = self._route_journeys(existing_objects)

        if send_to_hermes_add_auth:
            hermes_message = self._hermes_messaging_data()
            hermes_message["loyalty_card_id"] = old_card_id
            hermes_message["journey"] = DELETE
            send_message_to_hermes("delete_loyalty_card", hermes_message)

            # generate request event
            self._dispatch_request_event()
            self.send_to_hermes_add_auth()
        elif send_to_hermes_auth:
            self._dispatch_request_event()
            self.send_to_hermes_add_auth()

        return send_to_hermes_add_auth or send_to_hermes_auth

    def handle_register_card(self) -> bool:

        self.fetch_and_check_existing_card_links()
        send_to_hermes = self.register_journey_additional_checks()

        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials()
        self.validate_and_refactor_consents()

        if send_to_hermes:
            api_logger.info("Sending to Hermes for onward journey")
            hermes_message = self._hermes_messaging_data()
            hermes_message["register_fields"] = deepcopy(self.register_fields)
            hermes_message["consents"] = deepcopy(self.all_consents)
            send_message_to_hermes("loyalty_card_register", hermes_message)

        return send_to_hermes

    def handle_join_card(self):
        self.add_or_link_card(validate_consents=True)

        api_logger.info("Sending to Hermes for onward journey")
        hermes_message = self._hermes_messaging_data()
        hermes_message["join_fields"] = deepcopy(self.join_fields)
        hermes_message["consents"] = deepcopy(self.all_consents)
        send_message_to_hermes("loyalty_card_join", hermes_message)

    def handle_put_join(self):
        existing_card_link = self.fetch_and_check_single_card_user_link()
        self.link_to_user = existing_card_link

        if existing_card_link.link_status in LoyaltyCardStatus.JOIN_PENDING_STATES:
            raise falcon.HTTPConflict(
                code="JOIN_IN_PROGRESS", title="The Join cannot be updated while it is in Progress."
            )

        if existing_card_link.link_status not in LoyaltyCardStatus.JOIN_FAILED_STATES:
            raise falcon.HTTPConflict(
                code="JOIN_NOT_IN_FAILED_STATE", title="The Join can only be updated from a failed state."
            )

        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials()
        self.validate_and_refactor_consents()

        new_status = LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS
        user_association_query = (
            update(SchemeAccountUserAssociation)
            .where(SchemeAccountUserAssociation.id == existing_card_link.id)
            .values(link_status=new_status)
        )

        self.db_session.execute(user_association_query)
        self.db_session.commit()

        # Send to hermes to process join
        api_logger.info("Sending to Hermes for onward journey")
        hermes_message = self._hermes_messaging_data()
        hermes_message["join_fields"] = deepcopy(self.join_fields)
        hermes_message["consents"] = deepcopy(self.all_consents)
        send_message_to_hermes("loyalty_card_join", hermes_message)

    def handle_delete_join(self):
        existing_card_link = self.fetch_and_check_single_card_user_link()
        self.link_to_user = existing_card_link

        if existing_card_link.link_status in [
            LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
            LoyaltyCardStatus.JOIN_IN_PROGRESS,
        ]:
            raise falcon.HTTPConflict(
                code="JOIN_IN_PROGRESS", title="Loyalty card cannot be deleted until the Join process has completed"
            )
        # Only allow deletes where the link_status are in a failed join status
        if existing_card_link.link_status not in LoyaltyCardStatus.FAILED_JOIN_STATUS:
            raise falcon.HTTPConflict(code="CONFLICT", title="Could not process request due to a conflict")

        existing_card_link.scheme_account.is_deleted = True
        self.db_session.delete(existing_card_link)
        self.db_session.commit()

    def handle_delete_card(self) -> None:
        existing_card_link = self.fetch_and_check_single_card_user_link()
        self.link_to_user = existing_card_link

        if existing_card_link.link_status == LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS:
            raise falcon.HTTPConflict(
                code="JOIN_IN_PROGRESS", title="Loyalty card cannot be deleted until the Join process has completed"
            )

        hermes_message = self._hermes_messaging_data()
        send_message_to_hermes("delete_loyalty_card", hermes_message)

    def add_or_link_card(self, validate_consents: bool = False):
        """Starting point for most POST endpoints"""
        api_logger.info(f"Starting Loyalty Card '{self.journey}' journey")

        self.retrieve_plan_questions_and_answer_fields()

        self.validate_all_credentials()

        if validate_consents:
            self.validate_and_refactor_consents()

        created = self.link_user_to_existing_or_create()
        return created

    def fetch_and_check_single_card_user_link(self) -> SchemeAccountUserAssociation:
        existing_card_links = self.get_existing_card_links(only_this_user=True)
        if not existing_card_links:
            raise ResourceNotFoundError

        self.link_to_user = existing_card_links[0].SchemeAccountUserAssociation
        return self.link_to_user

    def get_existing_card_links(self, only_this_user=False) -> list[Row]:
        query = (
            select(SchemeAccountUserAssociation)
            .join(SchemeAccount)
            .where(SchemeAccount.id == self.card_id, SchemeAccount.is_deleted.is_(False))
        )

        if only_this_user:
            query = query.where(SchemeAccountUserAssociation.user_id == self.user_id)

        try:
            card_links = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty card links from database")
            raise falcon.HTTPInternalServerError

        return card_links

    def fetch_and_check_existing_card_links(self) -> None:
        """Fetches and performs basic checks on existing card links (as searched by id)."""

        card_links = self.get_existing_card_links()

        link_objects = []
        if card_links:
            for link in card_links:
                link_objects.append(link.SchemeAccountUserAssociation)

        for assoc in link_objects:
            if assoc.user_id == self.user_id:
                self.link_to_user = assoc

        # Card doesn't exist, or isn't linkable to this user
        if not link_objects or not self.link_to_user:
            raise ResourceNotFoundError

        self.card = card_links[0].SchemeAccountUserAssociation.scheme_account
        self.loyalty_plan_id = self.card.scheme.id
        self.loyalty_plan = self.card.scheme

    def register_journey_additional_checks(self) -> bool:

        if self.link_to_user.link_status == LoyaltyCardStatus.WALLET_ONLY:
            return True

        elif self.link_to_user.link_status in (
            LoyaltyCardStatus.REGISTRATION_IN_PROGRESS,
            LoyaltyCardStatus.REGISTRATION_ASYNC_IN_PROGRESS,
        ):
            # In the case of Registration in progress we just return the id of the registration process
            return False

        elif self.link_to_user.link_status == LoyaltyCardStatus.ACTIVE:
            raise falcon.HTTPConflict(
                code="ALREADY_REGISTERED",
                title="Card is already registered. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to authorise this"
                " card in your wallet, or to update authorisation credentials.",
            )

        else:
            # Catch-all for other statuses
            raise falcon.HTTPConflict(code="REGISTRATION_ERROR", title="Card cannot be registered at this time.")

    def get_existing_auth_answers(self) -> dict:
        query = (
            select(SchemeAccountCredentialAnswer, SchemeCredentialQuestion)
            .join(SchemeCredentialQuestion)
            .where(
                SchemeAccountCredentialAnswer.scheme_account_entry_id == self.link_to_user.id,
                SchemeCredentialQuestion.auth_field.is_(True),
            )
        )
        try:
            all_credential_answers = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        reply = {}
        cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

        for row in all_credential_answers:
            ans = row[0].answer
            credential_name = row[1].type
            if credential_name in ENCRYPTED_CREDENTIALS:
                ans = cipher.decrypt(ans)
            reply[credential_name] = ans
        return reply

    def _get_existing_merchant_identifiers(self, exclude_current_user: bool = False) -> Optional[str]:
        query = (
            select(SchemeAccountCredentialAnswer, SchemeCredentialQuestion)
            .join(SchemeCredentialQuestion)
            .join(SchemeAccountUserAssociation)
            .where(
                SchemeAccountUserAssociation.scheme_account_id == self.card_id,
                SchemeCredentialQuestion.type == MERCHANT_IDENTIFIER,
            )
        )

        if exclude_current_user:
            query = query.where(SchemeAccountUserAssociation.id != self.link_to_user.id)

        try:
            all_credential_answers = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        unique_answers = set([row[0].answer for row in all_credential_answers])

        if len(unique_answers) <= 1:
            answer = list(unique_answers)
            return answer[0] if answer else None
        else:
            loyalty_card_id = all_credential_answers[0].SchemeCredentialQuestion.scheme_id
            api_logger.error(f"Multiple merchant_identifiers found for Loyalty card id: {loyalty_card_id}")
            raise falcon.HTTPConflict()

    def _format_merchant_fields(self):
        merchant_fields = []
        for question, answer in self.all_answer_fields.get("merchant_fields", {}).items():
            field = {"credential_slug": question, "value": answer}
            merchant_fields.append(field)
        return merchant_fields

    def retrieve_plan_questions_and_answer_fields(self) -> None:
        """Gets loyalty plan and all associated questions and consents (in the case of consents: ones that are necessary
        for this journey type."""

        def _query_scheme_info():

            consent_type = CredentialClass.ADD_FIELD
            if self.journey in (ADD_AND_REGISTER, REGISTER):
                consent_type = CredentialClass.REGISTER_FIELD
            elif self.journey in (AUTHORISE, ADD_AND_AUTHORISE):
                consent_type = CredentialClass.AUTH_FIELD
            elif self.journey == JOIN:
                consent_type = CredentialClass.JOIN_FIELD

            # Fetches all questions, but only consents for the relevant journey type (i.e. register, join)
            query = (
                select(Scheme, SchemeCredentialQuestion, Consent)
                .select_from(Scheme)
                .join(SchemeCredentialQuestion)
                .join(SchemeChannelAssociation)
                .join(Channel)
                .join(ClientApplication)
                .outerjoin(
                    ThirdPartyConsentLink,
                    (ThirdPartyConsentLink.client_app_id == ClientApplication.client_id)
                    & (ThirdPartyConsentLink.scheme_id == Scheme.id)
                    & (getattr(ThirdPartyConsentLink, consent_type) == "true"),
                )
                .outerjoin(Consent, Consent.id == ThirdPartyConsentLink.consent_id)
                .where(
                    SchemeCredentialQuestion.scheme_id == self.loyalty_plan_id,
                    Channel.bundle_id == self.channel_id,
                    SchemeChannelAssociation.status == LoyaltyPlanChannelStatus.ACTIVE.value,
                )
            )

            try:
                all_credential_questions_and_plan_output = self.db_session.execute(query).all()
            except DatabaseError:
                api_logger.error("Unable to fetch loyalty plan records from database")
                raise falcon.HTTPInternalServerError

            return all_credential_questions_and_plan_output

        try:
            self.add_fields = self.all_answer_fields.get("add_fields", {}).get("credentials", [])
            self.auth_fields = self.all_answer_fields.get("authorise_fields", {}).get("credentials", [])
            self.register_fields = self.all_answer_fields.get("register_ghost_card_fields", {}).get("credentials", [])
            self.join_fields = self.all_answer_fields.get("join_fields", {}).get("credentials", [])
            # These are provided slightly differently to the other credentials so needs some formatting
            self.merchant_fields = self._format_merchant_fields()

        except KeyError:
            api_logger.exception("KeyError when processing answer fields")
            raise falcon.HTTPInternalServerError

        all_credential_questions_and_plan = _query_scheme_info()

        if len(all_credential_questions_and_plan) < 1:
            api_logger.error(
                "Loyalty plan does not exist, is not available for this channel, or no credential questions found"
            )
            raise ValidationError

        self.loyalty_plan = all_credential_questions_and_plan[0][0]

        all_questions = [row[1] for row in all_credential_questions_and_plan]
        self.plan_credential_questions = self._format_questions(all_questions)
        self.plan_consent_questions = list({row.Consent for row in all_credential_questions_and_plan if row.Consent})

    def validate_all_credentials(self, auth_require_all: bool = True) -> None:
        """Cross-checks available plan questions with provided answers.
        Then populates a final list of validated credentials."""

        self.valid_credentials = {}

        # Validates credentials per credential class.
        # No need to relate this to with journey type - this is done in request validation.
        if self.add_fields:
            self._validate_credentials_by_class(self.add_fields, CredentialClass.ADD_FIELD)
        if self.auth_fields:
            self._validate_credentials_by_class(
                self.auth_fields, CredentialClass.AUTH_FIELD, require_all=auth_require_all
            )
        if self.register_fields:
            self._validate_credentials_by_class(self.register_fields, CredentialClass.REGISTER_FIELD, require_all=True)
        if self.join_fields:
            self._validate_credentials_by_class(self.join_fields, CredentialClass.JOIN_FIELD, require_all=True)
        if self.merchant_fields:
            self._validate_credentials_by_class(self.merchant_fields, "merchant_field", require_all=True)

        # Checks that at least one manual question, scan question or one question link has been given.
        for key, cred in self.valid_credentials.items():
            if cred["key_credential"]:
                self.key_credential = cred

        # Authorise, Register, Join journeys do not require a key credential
        if not self.key_credential and self.journey not in (AUTHORISE, REGISTER, JOIN):
            err_msg = "At least one manual question, scan question or one question link must be provided."
            api_logger.error(err_msg)
            raise ValidationError

    def validate_and_refactor_consents(self) -> None:
        """Checks necessary consents are present, and that present consents are necessary. Refactors into a
        hermes-friendly format for later hermes-side processing."""

        consent_locations = ["authorise_fields", "add_fields", "join_fields", "register_ghost_card_fields"]

        found_class_consents = []
        for consent_location in consent_locations:
            found_class_consents.extend(
                [i for i in self.all_answer_fields.get(consent_location, {}).get("consents", [])]
            )

        self.all_consents = []
        if self.plan_consent_questions or found_class_consents:
            # We check the consents if any are provided, or if any are required:

            for consent in found_class_consents:
                for consent_question in self.plan_consent_questions:
                    if consent["consent_slug"] == consent_question.slug:
                        self.all_consents.append({"id": consent_question.id, "value": consent["value"]})

            if not len(found_class_consents) == len(self.plan_consent_questions) == len(self.all_consents):
                raise ValidationError

    @staticmethod
    def _process_case_sensitive_credentials(credential_slug: str, credential: str) -> str:
        return credential.lower() if credential_slug not in CASE_SENSITIVE_CREDENTIALS else credential

    def _check_answer_has_matching_question(self, answer: dict, credential_class: CredentialClass) -> None:
        try:
            question = self.plan_credential_questions[credential_class][answer["credential_slug"]]
            answer["value"] = self._process_case_sensitive_credentials(answer["credential_slug"], answer["value"])
            # Checks if this cred is the 'key credential' which will effectively act as the pk for the
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

    def _validate_credentials_by_class(
        self, answer_set: Iterable[dict], credential_class: Union[CredentialClass, str], require_all: bool = False
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

    def link_user_to_existing_or_create(self) -> bool:

        if self.journey == JOIN:
            existing_objects = []
        else:
            existing_objects = self._get_existing_objects_by_key_cred()

        created = self._route_journeys(existing_objects)
        return created

    def _get_existing_objects_by_key_cred(self) -> list[Row[SchemeAccount, SchemeAccountUserAssociation, Scheme]]:
        key_credential_field = self._get_key_credential_field()

        query = (
            select(SchemeAccount, SchemeAccountUserAssociation, Scheme)
            .join(SchemeAccountUserAssociation)
            .join(Scheme)
            .where(
                getattr(SchemeAccount, key_credential_field) == self.key_credential["credential_answer"],
                SchemeAccount.scheme_id == self.loyalty_plan_id,
                SchemeAccount.is_deleted.is_(False),
            )
        )

        try:
            existing_objects = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch matching loyalty cards from database")
            raise falcon.HTTPInternalServerError

        return existing_objects

    def _existing_objects_by_merchant_identifier(self) -> list[Row]:
        merchant_identifier = None
        for credential in self.merchant_fields:
            if credential["credential_slug"] == MERCHANT_IDENTIFIER:
                merchant_identifier = credential["value"]
                break

        if not merchant_identifier:
            return []

        query = (
            select(SchemeAccount, SchemeAccountUserAssociation, Scheme)
            .join(SchemeAccountUserAssociation)
            .join(Scheme)
            .where(
                SchemeAccount.merchant_identifier == merchant_identifier,
                SchemeAccount.scheme_id == self.loyalty_plan_id,
                SchemeAccount.is_deleted.is_(False),
            )
        )

        try:
            existing_objects = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch matching loyalty cards from database")
            raise falcon.HTTPInternalServerError

        return existing_objects

    def _validate_key_cred_matches_merchant_identifier(self, existing_objects: list) -> None:
        """Since both the key credential and merchant identifier are used to identify a loyalty card,
        they have a unique together relationship which must be validated.
        This isn't done on the database level due to multiple fields being used for the key credential.
        """
        existing_key_cred_answers = set()
        for row in existing_objects:
            scheme_account_key_fields = (
                row.SchemeAccount.card_number,
                row.SchemeAccount.barcode,
                row.SchemeAccount.alt_main_answer,
            )
            key_cred_answer = [answer for answer in scheme_account_key_fields if answer][0]
            existing_key_cred_answers.add(key_cred_answer)

        existing_answer_count = len(existing_key_cred_answers)
        if existing_answer_count == 1:
            # check the given key cred matches the existing account's
            if self.key_credential["credential_answer"] != list(existing_key_cred_answers)[0]:
                raise ValidationError(
                    "An account with the given merchant identifier already exists, but the key credential doesn't match"
                )
        elif existing_answer_count > 1:
            # If the code above works this should never happen
            scheme = existing_objects[0].Scheme.name
            card_ids = [row.SchemeAccount.id for row in existing_objects]
            err = f"Multiple accounts with the same merchant identifier for {scheme} - " f"Loyalty Card ids: {card_ids}"
            api_logger.error(err)
            raise ValidationError(err)

    def _no_card_route(self) -> bool:
        self.create_new_loyalty_card()
        return True

    def _single_card_route(self, existing_scheme_account_ids, existing_objects):
        created = False

        self.card_id = existing_scheme_account_ids[0]
        api_logger.info(f"Existing loyalty card found: {self.card_id}")

        # existing_card = existing_objects[0].SchemeAccount
        existing_links = list({item.SchemeAccountUserAssociation for item in existing_objects})

        # Reset to None in case the user is updating to a different card
        self.link_to_user = None
        for link in existing_links:
            if link.user_id == self.user_id:
                self.link_to_user = link

        if self.journey == ADD_AND_REGISTER:
            created = self._route_add_and_register(existing_links)

        elif self.journey == ADD_AND_AUTHORISE:
            created = self._route_add_and_authorise()

        elif self.journey == TRUSTED_ADD:
            created = self._route_trusted_add()

        elif not self.link_to_user:
            self.link_account_to_user()

        return created

    def _route_journeys(self, existing_objects: list) -> bool:

        existing_scheme_account_ids = []

        for item in existing_objects:
            existing_scheme_account_ids.append(item.SchemeAccount.id)

        number_of_existing_accounts = len(set(existing_scheme_account_ids))

        if number_of_existing_accounts == 0:
            self._no_card_route()
            created = True

        elif number_of_existing_accounts == 1:
            created = self._single_card_route(
                existing_scheme_account_ids=existing_scheme_account_ids, existing_objects=existing_objects
            )

        else:
            api_logger.error(f"Multiple Loyalty Cards found with matching information: {existing_scheme_account_ids}")
            raise falcon.HTTPInternalServerError

        return created

    def check_auth_credentials_against_existing(self) -> tuple[bool, bool]:
        existing_auths = self.get_existing_auth_answers()
        all_match = True
        if existing_auths:
            for item in self.auth_fields:
                qname = item["credential_slug"]
                if existing_auths[qname] != item["value"]:
                    all_match = False
                    break

        if not all_match:
            self._dispatch_request_event()
            self._dispatch_outcome_event(success=False)

        elif existing_auths and all_match:
            self._dispatch_request_event()
            self._dispatch_outcome_event(success=True)

        existing_credentials = True if existing_auths else False
        return existing_credentials, all_match

    def validate_merchant_identifier(self) -> Optional[bool]:
        # This is somewhat inefficient since link_user_to_existing_or_create will also do some validation
        # to check for existing accounts with the add field. This endpoint requires some unique checks
        # surrounding the merchant_identifier, so it's validated here to prevent changes to code shared
        # across the other endpoints.
        existing_objects = self._existing_objects_by_merchant_identifier()
        if existing_objects:
            try:
                self._validate_key_cred_matches_merchant_identifier(existing_objects)
            except ValidationError:
                err = (
                    "A loyalty card with this account_id has already been added in a wallet, "
                    "but the key credential does not match."
                )
                api_logger.debug(err)
                raise falcon.HTTPConflict(code="CONFLICT", title=err)

        return bool(existing_objects)

    def _check_merchant_identifier_against_existing(
        self, exclude_current_user: bool = False
    ) -> tuple[Optional[bool], bool]:
        existing_merchant_identifier = self._get_existing_merchant_identifiers(exclude_current_user)
        match = False
        if existing_merchant_identifier:
            for item in self.merchant_fields:
                if item["credential_slug"] == MERCHANT_IDENTIFIER:
                    if existing_merchant_identifier == item["value"]:
                        match = True
                        break
        return bool(existing_merchant_identifier), match

    def _dispatch_outcome_event(self, success: bool) -> None:
        hermes_message = self._hermes_messaging_data()
        hermes_message["success"] = success
        send_message_to_hermes("add_auth_outcome_event", hermes_message)

    def _dispatch_request_event(self) -> None:
        hermes_message = self._hermes_messaging_data()
        send_message_to_hermes("add_auth_request_event", hermes_message)

    def _route_trusted_add(self) -> bool:
        # Handles TRUSTED_ADD behaviour in the case of existing Loyalty Card <> User links
        created = False

        # Check if given merchant identifier matches those existing
        merchant_identifier_exists, match = self._check_merchant_identifier_against_existing()

        if merchant_identifier_exists and not match:
            err = (
                "A loyalty card with this key credential has already been added in a wallet, "
                "but the account_id does not match."
            )
            raise falcon.HTTPConflict(code="CONFLICT", title=err)

        if not self.link_to_user:
            self.link_account_to_user(link_status=LoyaltyCardStatus.ACTIVE)
            created = True

        return created

    def _route_add_and_authorise(self) -> bool:
        # Handles ADD AND AUTH behaviour in the case of existing Loyalty Card <> User links

        # a link exists to *this* user (Single Wallet Scenario)
        if self.link_to_user:
            if self.link_to_user.link_status in LoyaltyCardStatus.AUTH_IN_PROGRESS:
                created = False
            elif self.link_to_user.link_status == LoyaltyCardStatus.ACTIVE:
                existing_creds, match_all = self.check_auth_credentials_against_existing()

                if existing_creds and match_all:
                    # No change - we return a 200
                    created = False

                elif existing_creds and not match_all:
                    raise falcon.HTTPConflict(
                        code="ALREADY_AUTHORISED",
                        title="Card already authorised. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to modify"
                        " authorisation credentials.",
                    )

                else:
                    api_logger.error("Card status is ACTIVE but no auth credentials found!")
                    raise falcon.HTTPInternalServerError
            else:
                # All other cases where user is already linked to this account
                raise falcon.HTTPConflict(
                    code="ALREADY_ADDED",
                    title="Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to authorise this "
                    "card.",
                )
        # a link exists to *a different* user ( Multi-wallet Schenario)
        else:
            self.link_account_to_user()
            # Although no account has actually been created, a new link to this user has, and we need to return a 202
            # and signal hermes to pick this up and auth.
            created = True

        return created

    def _route_add_and_register(self, existing_links: list) -> bool:
        # Handles ADD_AND_REGISTER behaviour in the case of existing Loyalty Card <> User links
        # a link exists to *this* user (Single Wallet Scenario)
        if self.link_to_user:
            if self.link_to_user.link_status == LoyaltyCardStatus.ACTIVE:
                raise falcon.HTTPConflict(
                    code="ALREADY_REGISTERED",
                    title="Card is already registered. Use POST "
                    "/loyalty_cards/add_and_authorise to add this "
                    "card to your wallet.",
                )
            elif self.link_to_user.link_status in LoyaltyCardStatus.REGISTRATION_IN_PROGRESS:
                created = False
            else:
                raise falcon.HTTPConflict(
                    code="ALREADY_ADDED",
                    title="Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/register to register this "
                    "card.",
                )

        # a link exists to *a different* user (Multi-wallet Scenario)
        else:
            is_unregistered = all(link.link_status == LoyaltyCardStatus.WALLET_ONLY for link in existing_links)
            is_in_progress = any(
                link.link_status == LoyaltyCardStatus.REGISTRATION_IN_PROGRESS for link in existing_links
            )
            if is_unregistered:
                created = True
                self.link_account_to_user(link_status=LoyaltyCardStatus.WALLET_ONLY)
            elif is_in_progress:
                raise falcon.HTTPConflict(
                    code="REGISTRATION_ALREADY_IN_PROGRESS",
                    title="Card cannot be registered at this time"
                    " - an existing registration is still in progress in "
                    "another wallet.",
                )
            else:
                raise falcon.HTTPConflict(
                    code="REGISTRATION_ERROR",
                    title="Card cannot be registered at this time.",
                )
        return created

    @staticmethod
    def _generate_card_number_from_barcode(loyalty_plan: Scheme, barcode: str) -> str:
        try:
            regex_match = re.search(loyalty_plan.card_number_regex, barcode)
            if regex_match:
                return loyalty_plan.card_number_prefix + regex_match.group(1)
        except (sre_constants.error, ValueError):
            api_logger.warning("Failed to convert barcode to card_number")

    @staticmethod
    def _generate_barcode_from_card_number(loyalty_plan: Scheme, card_number: str) -> str:
        try:
            regex_match = re.search(loyalty_plan.barcode_regex, card_number)
            if regex_match:
                return loyalty_plan.barcode_prefix + regex_match.group(1)
        except (sre_constants.error, ValueError):
            api_logger.warning("Failed to convert card_number to barcode")

    def _get_card_number_and_barcode(self) -> tuple[str, str]:
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

    def create_new_loyalty_card(self) -> None:
        card_number, barcode = self._get_card_number_and_barcode()
        merchant_identifier = None

        journey_map = {
            ADD: {
                "new_status": LoyaltyCardStatus.WALLET_ONLY,
                "originating_journey": OriginatingJourney.ADD,
            },
            TRUSTED_ADD: {
                "new_status": LoyaltyCardStatus.ACTIVE,
                "originating_journey": OriginatingJourney.ADD,
            },
            ADD_AND_AUTHORISE: {
                "new_status": LoyaltyCardStatus.PENDING,
                "originating_journey": OriginatingJourney.ADD,
            },
            ADD_AND_REGISTER: {
                # todo: These should likely be a registration in progress state for consistency with join
                #  and raised as tech debt. Not currently an issue since it is changed to this status in hermes
                "new_status": LoyaltyCardStatus.PENDING,
                # todo: This should also probably be Add for consistency with ADD_AND_AUTH.
                #  Need to discuss with data team?
                "originating_journey": OriginatingJourney.REGISTER,
            },
            REGISTER: {
                "new_status": LoyaltyCardStatus.PENDING,
                "originating_journey": OriginatingJourney.REGISTER,
            },
            JOIN: {
                "new_status": LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
                "originating_journey": OriginatingJourney.JOIN,
            },
        }

        new_status = journey_map[self.journey]["new_status"]
        originating_journey = journey_map[self.journey]["originating_journey"]

        if self.journey == TRUSTED_ADD:
            merchant_identifier = [
                item["value"] for item in self.merchant_fields if item["credential_slug"] == MERCHANT_IDENTIFIER
            ][0]

        if self.key_credential and self._get_key_credential_field() == "alt_main_answer":
            alt_main_answer = self.key_credential["credential_answer"]
        else:
            alt_main_answer = ""

        loyalty_card = SchemeAccount(
            order=1,
            created=datetime.now(),
            updated=datetime.now(),
            card_number=card_number or "",
            barcode=barcode or "",
            alt_main_answer=alt_main_answer,
            merchant_identifier=merchant_identifier or "",
            scheme_id=self.loyalty_plan_id,
            is_deleted=False,
            balances={},
            vouchers={},
            transactions=[],
            pll_links=[],
            formatted_images={},
            originating_journey=originating_journey,
        )

        self.db_session.add(loyalty_card)
        self.db_session.flush()

        self.card_id = loyalty_card.id

        self.link_account_to_user(link_status=new_status)

        api_logger.info(f"Created Loyalty Card {self.card_id}")

    def link_account_to_user(self, link_status: int = LoyaltyCardStatus.PENDING) -> None:
        api_logger.info(f"Linking Loyalty Card {self.card_id} to User Account {self.user_id}")
        if self.journey == ADD:
            link_status = LoyaltyCardStatus.WALLET_ONLY

        # By default, we set status to PENDING (ap=True) or WALLET_ONLY (ap=False), unless overridden in args.
        user_association_object = SchemeAccountUserAssociation(
            scheme_account_id=self.card_id, user_id=self.user_id, link_status=link_status
        )

        self.db_session.add(user_association_object)
        try:
            # Commits new loyalty card (if appropriate), as well as link to user.
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

        self.link_to_user = user_association_object

    def _hermes_messaging_data(self) -> dict:
        return {
            "loyalty_plan_id": self.loyalty_plan_id,
            "loyalty_card_id": self.card_id,
            "entry_id": self.link_to_user.id,
            "user_id": self.user_id,
            "channel_slug": self.channel_id,
            "journey": self.journey,
            "auto_link": True,
        }

    def _auth_field_manual_question_hack(self, hermes_message: dict) -> None:
        # Fix for Harvey Nichols/Squaremeal
        # Remove main answer from auth fields as this should have been saved already and hermes raises a
        # validation error if provided
        if self.key_credential and hermes_message["authorise_fields"]:
            for index, auth_field in enumerate(hermes_message["authorise_fields"]):
                if auth_field["credential_slug"] == self.key_credential["credential_type"]:
                    cred = hermes_message["authorise_fields"].pop(index)
                    self.add_fields = [cred]
                    break

    def send_to_hermes_add_auth(self) -> None:
        api_logger.info("Sending to Hermes for onward authorisation")
        hermes_message = self._hermes_messaging_data()
        hermes_message["consents"] = deepcopy(self.all_consents)
        hermes_message["authorise_fields"] = deepcopy(self.auth_fields)

        self._auth_field_manual_question_hack(hermes_message)

        hermes_message["add_fields"] = deepcopy(self.add_fields)
        send_message_to_hermes("loyalty_card_add_auth", hermes_message)

    def send_to_hermes_add_only(self) -> None:
        api_logger.info("Sending to Hermes for credential writing")
        hermes_message = self._hermes_messaging_data()
        hermes_message["add_fields"] = deepcopy(self.add_fields)
        send_message_to_hermes("loyalty_card_add", hermes_message)

    def send_to_hermes_trusted_add(self) -> None:
        api_logger.info("Sending to Hermes for PLL and credential processing")
        hermes_message = self._hermes_messaging_data()
        hermes_message["consents"] = deepcopy(self.all_consents)
        hermes_message["authorise_fields"] = deepcopy(self.auth_fields)
        hermes_message["merchant_fields"] = deepcopy(self.merchant_fields)

        self._auth_field_manual_question_hack(hermes_message)

        hermes_message["add_fields"] = deepcopy(self.add_fields)
        send_message_to_hermes("loyalty_card_trusted_add", hermes_message)

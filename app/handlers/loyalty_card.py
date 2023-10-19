import re
import sre_constants
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import arrow
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
from app.lib.credentials import (
    BARCODE,
    CARD_NUMBER,
    CASE_SENSITIVE_CREDENTIALS,
    ENCRYPTED_CREDENTIALS,
    MERCHANT_IDENTIFIER,
)
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


PlanCredentialQuestionsType = dict[CredentialClass | str, dict[QuestionType | str, SchemeCredentialQuestion]]


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
    all_answer_fields: dict = None  # type: ignore [assignment]
    loyalty_plan_id: int = None  # type: ignore [assignment]
    loyalty_plan: Scheme = None  # type: ignore [assignment]
    add_fields: list = None  # type: ignore [assignment]
    auth_fields: list = None  # type: ignore [assignment]
    register_fields: list = None  # type: ignore [assignment]
    join_fields: list = None  # type: ignore [assignment]
    merchant_fields: list[dict[str, str]] = None  # type: ignore [assignment]
    valid_credentials: dict = None  # type: ignore [assignment]
    key_credential: dict = None  # type: ignore [assignment]
    merchant_identifier: str | None = None
    all_consents: list = None  # type: ignore [assignment]
    link_to_user: SchemeAccountUserAssociation | None = None
    card_id: int = None  # type: ignore [assignment]
    card: SchemeAccount = None  # type: ignore [assignment]
    plan_credential_questions: PlanCredentialQuestionsType = None  # type: ignore [assignment]
    plan_consent_questions: list[Consent] = None  # type: ignore [assignment]

    cred_types: list = None  # type: ignore [assignment]

    @property
    def not_none_link_to_user(self) -> SchemeAccountUserAssociation:
        if not self.link_to_user:
            raise ValueError("self.link_to_user value is unexpectedly None")

        return self.link_to_user

    @staticmethod
    def _format_questions(
        all_credential_questions: Iterable[SchemeCredentialQuestion],
    ) -> dict[CredentialClass | str, dict[QuestionType | str, SchemeCredentialQuestion]]:
        """Restructures credential questions for easier access of questions by CredentialClass and QuestionType"""

        formatted_questions: dict[str, dict] = {cred_class.value: {} for cred_class in CredentialClass}
        for question in all_credential_questions:
            for cred_class in CredentialClass:
                if getattr(question, cred_class):
                    formatted_questions[cred_class][question.type] = question

            # Collect any additional merchant fields required for trusted channels.
            if question.third_party_identifier:
                formatted_questions["merchant_field"] = {}
                formatted_questions["merchant_field"][question.type] = question

        return formatted_questions

    def _get_key_credential_field(self) -> str:
        if self.key_credential and self.key_credential["credential_type"] in (
            QuestionType.CARD_NUMBER,
            QuestionType.BARCODE,
        ):
            key_credential_field = self.key_credential["credential_type"]
        else:
            key_credential_field = "alt_main_answer"

        return key_credential_field

    def _get_merchant_identifier(self) -> str | None:
        """
        Retrieves the merchant identifier from the given set of credentials in the request body.
        Must be called in or after retrieve_plan_questions_and_answer_fields so self.merchant_fields is populated
        """
        merchant_identifier: str | None = None

        if self.merchant_identifier:
            merchant_identifier = self.merchant_identifier

        elif self.merchant_fields:
            for credential in self.merchant_fields:
                if credential["credential_slug"] == MERCHANT_IDENTIFIER:
                    merchant_identifier = credential["value"]
                    break

            self.merchant_identifier = merchant_identifier

        return merchant_identifier

    def handle_add_only_card(self) -> bool:
        self.retrieve_credentials_and_validate()
        created = self.link_user_to_existing_or_create()

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
            and not self.merchant_identifier
            or getattr(self.card, self._get_key_credential_field(), None) == self.key_credential["credential_answer"]
            and self.card.merchant_identifier == self.merchant_identifier
        ):
            # Route for when neither the key credential nor merchant identifier are being updated.
            # Since these two fields are the only updatable fields for this endpoint, this means that
            # the user is attempting to update a card already in their wallet with the same credentials.
            # Do nothing.
            pass

        else:
            self.validate_merchant_identifier(exclude_current_user_link=True)
            existing_objects = self._get_existing_objects_by_key_cred(exclude_current_user_link=True)
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
        self.retrieve_credentials_and_validate(validate_consents=True)

        # Additional validation specific to this endpoint
        # If the loyalty plan requires authorisation, do not allow an add-field-only link
        if (self.add_fields and not self.auth_fields) and self.loyalty_plan.authorisation_required:
            raise ValidationError("This loyalty plan requires authorise fields to use this endpoint")

        send_to_hermes = self.link_user_to_existing_or_create()

        self._dispatch_request_event()
        if send_to_hermes:
            self.send_to_hermes_add_auth()
        return send_to_hermes

    def handle_add_register_card(self) -> bool:
        self.retrieve_credentials_and_validate(validate_consents=True)
        send_to_hermes = self.link_user_to_existing_or_create()

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
            # We will only NOT send to hermes if this user's credentials match what they already have
            existing_creds, matching_creds = self.check_auth_credentials_against_existing()
            send_to_hermes_auth = not (existing_creds and matching_creds)

            if not send_to_hermes_auth:
                # We still want to fire request and outcome event even if credentials are the same
                # lc.auth.success if link_status is authorised
                # lc.auth.failed for all other states
                self._dispatch_request_event()
                if self.not_none_link_to_user.link_status == LoyaltyCardStatus.ACTIVE:
                    self._dispatch_outcome_event(success=True)
                else:
                    self._dispatch_outcome_event(success=False)

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

    def handle_update_register_card(self) -> bool:
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

    def handle_join_card(self) -> None:
        self.retrieve_credentials_and_validate(validate_consents=True)
        self.link_user_to_existing_or_create()

        api_logger.info("Sending to Hermes for onward journey")
        hermes_message = self._hermes_messaging_data()
        hermes_message["join_fields"] = deepcopy(self.join_fields)
        hermes_message["consents"] = deepcopy(self.all_consents)
        send_message_to_hermes("loyalty_card_join", hermes_message)

    def handle_put_join(self) -> None:
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

    def handle_delete_join(self) -> None:
        existing_card_link = self.fetch_and_check_single_card_user_link()
        self.link_to_user = existing_card_link

        if existing_card_link.link_status in (
            LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
            LoyaltyCardStatus.JOIN_IN_PROGRESS,
        ):
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

    def retrieve_credentials_and_validate(self, validate_consents: bool = False) -> None:
        """Starting point for most POST endpoints"""
        api_logger.info(f"Starting Loyalty Card '{self.journey}' journey")

        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials()

        if validate_consents:
            self.validate_and_refactor_consents()

    def fetch_and_check_single_card_user_link(self) -> SchemeAccountUserAssociation:
        existing_card_links = self.get_existing_card_links(only_this_user=True)
        if not existing_card_links:
            raise ResourceNotFoundError

        self.link_to_user = existing_card_links[0].SchemeAccountUserAssociation
        return self.not_none_link_to_user

    def get_existing_card_links(self, only_this_user: bool = False) -> list[Row]:
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
            raise falcon.HTTPInternalServerError from None

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
        if self.not_none_link_to_user.link_status in (
            LoyaltyCardStatus.WALLET_ONLY,
            *LoyaltyCardStatus.REGISTRATION_FAILED_STATES,
        ):
            return True

        elif self.not_none_link_to_user.link_status in LoyaltyCardStatus.REGISTRATION_IN_PROGRESS:
            # In the case of Registration in progress we just return the id of the registration process
            return False

        elif self.not_none_link_to_user.link_status in (
            LoyaltyCardStatus.ACTIVE,
            LoyaltyCardStatus.PRE_REGISTERED_CARD,
        ):
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
                SchemeAccountCredentialAnswer.scheme_account_entry_id == self.not_none_link_to_user.id,
                SchemeCredentialQuestion.auth_field.is_(True),
            )
        )
        try:
            all_credential_answers = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError from None

        reply = {}
        cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

        for row in all_credential_answers:
            ans = row[0].answer
            credential_name = row[1].type
            if credential_name in ENCRYPTED_CREDENTIALS:
                ans = cipher.decrypt(ans)
            reply[credential_name] = ans
        return reply

    def _format_merchant_fields(self) -> list:
        merchant_fields = []
        for question, answer in self.all_answer_fields.get("merchant_fields", {}).items():
            field = {"credential_slug": question, "value": answer}
            merchant_fields.append(field)
        return merchant_fields

    def retrieve_plan_questions_and_answer_fields(self) -> None:
        """Gets loyalty plan and all associated questions and consents (in the case of consents: ones that are necessary
        for this journey type."""

        def _query_scheme_info() -> list:
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
                raise falcon.HTTPInternalServerError from None

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
            raise falcon.HTTPInternalServerError from None

        all_credential_questions_and_plan = _query_scheme_info()

        if len(all_credential_questions_and_plan) < 1:
            api_logger.error(
                "Loyalty plan does not exist, is not available for this channel, or no credential questions found"
            )
            raise ValidationError

        self.loyalty_plan = all_credential_questions_and_plan[0][0]

        all_questions: list[SchemeCredentialQuestion] = [row[1] for row in all_credential_questions_and_plan]
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
        for _key, cred in self.valid_credentials.items():
            if cred["key_credential"]:
                self.key_credential = cred

        # Sets merchant_identifier if provided (trusted channel)
        self._get_merchant_identifier()

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
            found_class_consents.extend(list(self.all_answer_fields.get(consent_location, {}).get("consents", [])))

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

    def _check_answer_has_matching_question(self, answer: dict, credential_class: CredentialClass | str) -> None:
        try:
            question = self.plan_credential_questions[credential_class][answer["credential_slug"]]
            answer["value"] = self._process_case_sensitive_credentials(answer["credential_slug"], answer["value"])
            # Checks if this cred is the 'key credential' which will effectively act as the pk for the
            # existing account search later on. There should only be one (this is checked later)
            key_credential = any(
                [
                    question.manual_question,
                    question.scan_question,
                    question.one_question_link,
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
            raise ValidationError from None

    def _validate_credentials_by_class(
        self, answer_set: Iterable[dict], credential_class: CredentialClass | str, require_all: bool = False
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

        if credential_class in (CredentialClass.REGISTER_FIELD, CredentialClass.JOIN_FIELD):
            credential_slugs = list(required_questions.keys())
            for slug in credential_slugs:
                if required_questions[slug].is_optional:
                    required_questions.pop(slug, None)

        if require_all and bool(required_questions):
            err_msg = f"Missing required {credential_class} credential(s) {list(required_questions.keys())}"
            api_logger.error(err_msg)
            raise ValidationError

    def link_user_to_existing_or_create(self) -> bool:
        existing_objects = [] if self.journey == JOIN else self._get_existing_objects_by_key_cred()

        created = self._route_journeys(existing_objects)
        return created

    def _get_existing_objects_by_key_cred(
        self, exclude_current_user_link: bool = False
    ) -> list[Row[SchemeAccount, SchemeAccountUserAssociation, Scheme]]:
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

        # Ignore the existing account for updates if it's only linked to the user
        if exclude_current_user_link:
            query = query.where(SchemeAccountUserAssociation.id != self.not_none_link_to_user.id)

        try:
            existing_objects = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch matching loyalty cards from database")
            raise falcon.HTTPInternalServerError from None

        return existing_objects

    def _existing_objects_by_merchant_identifier(self, exclude_current_user_link: bool = False) -> list[Row]:
        merchant_identifier = self._get_merchant_identifier()

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

        # Ignore the existing account for updates if it's only linked to the user
        if exclude_current_user_link:
            query = query.where(SchemeAccountUserAssociation.id != self.not_none_link_to_user.id)

        try:
            existing_objects = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch matching loyalty cards from database")
            raise falcon.HTTPInternalServerError from None

        return existing_objects

    def _validate_key_cred_matches_merchant_identifier(self, existing_objects: list) -> None:
        """Since both the key credential and merchant identifier are used to identify a loyalty card,
        they have a unique together relationship which must be validated.
        This isn't done on the database level due to multiple fields being used for the key credential.
        """
        # The scheme account field for the key identifier (card_number/barcode/alt_main_answer)
        if self.key_credential["credential_type"] == CARD_NUMBER:
            key_cred_field = CARD_NUMBER
        elif self.key_credential["credential_type"] == BARCODE:
            key_cred_field = BARCODE
        else:
            key_cred_field = "alt_main_answer"

        existing_key_cred_answers = {getattr(row.SchemeAccount, key_cred_field) for row in existing_objects}

        existing_answer_count = len(existing_key_cred_answers)
        if existing_answer_count == 1:
            # check the given key cred matches the existing account's
            if self.key_credential["credential_answer"] != next(iter(existing_key_cred_answers)):
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

    def _handle_add_conflict(self) -> None:
        code = "ALREADY_ADDED"
        title = "Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/register to register this card."

        if self.not_none_link_to_user.link_status == LoyaltyCardStatus.ACTIVE:
            code = "ALREADY_REGISTERED"
            title = (
                "Card is already registered. "
                "Use POST /loyalty_cards/add_and_authorise to add this card to your wallet."
            )
        raise falcon.HTTPConflict(
            code=code,
            title=title,
        )

    def _single_card_route(self, existing_scheme_account_ids: list[int], existing_objects: list[SchemeAccount]) -> bool:
        created = False

        self.card_id = existing_scheme_account_ids[0]
        api_logger.info(f"Existing loyalty card found: {self.card_id}")

        existing_card = existing_objects[0].SchemeAccount
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
            created = self._route_trusted_add(existing_card)

        elif not self.link_to_user:
            self.link_account_to_user()

        elif self.link_to_user and self.journey == ADD:
            # raise CONFLICT when adding the same card to same wallet
            self._handle_add_conflict()

        return created

    def _route_journeys(self, existing_objects: list) -> bool:
        existing_scheme_account_ids = [item.SchemeAccount.id for item in existing_objects]
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

        existing_credentials = bool(existing_auths)
        return existing_credentials, all_match

    def validate_merchant_identifier(self, exclude_current_user_link: bool = False) -> bool | None:
        # This is somewhat inefficient since link_user_to_existing_or_create will also do some validation
        # to check for existing accounts with the add field. This endpoint requires some unique checks
        # surrounding the merchant_identifier, so it's validated here to prevent changes to code shared
        # across the other endpoints.
        existing_objects = self._existing_objects_by_merchant_identifier(exclude_current_user_link)
        if existing_objects:
            try:
                self._validate_key_cred_matches_merchant_identifier(existing_objects)
            except ValidationError:
                err = (
                    "A loyalty card with this account_id has already been added in a wallet, "
                    "but the key credential does not match."
                )
                api_logger.debug(err)
                raise falcon.HTTPConflict(code="CONFLICT", title=err) from None

        return bool(existing_objects)

    def _check_merchant_identifier_against_existing(
        self,
        existing_card: SchemeAccount,
    ) -> tuple[bool | None, bool]:
        existing_merchant_identifier = existing_card.merchant_identifier

        match = False
        if existing_merchant_identifier:
            for item in self.merchant_fields:
                if item["credential_slug"] == MERCHANT_IDENTIFIER and existing_merchant_identifier == item["value"]:
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

    def _route_trusted_add(self, existing_card: SchemeAccount) -> bool:
        # Handles TRUSTED_ADD behaviour in the case of existing Loyalty Card <> User links
        created = False
        commit = False

        merchant_identifier_exists, match = self._check_merchant_identifier_against_existing(existing_card)

        if merchant_identifier_exists and not match:
            err = (
                "A loyalty card with this key credential has already been added in a wallet, "
                "but the account_id does not match."
            )
            raise falcon.HTTPConflict(code="CONFLICT", title=err)

        if not self.link_to_user:
            self.link_account_to_user(link_status=LoyaltyCardStatus.ACTIVE)
            created = True

        # Check active status in case the user has initially attempted to add the card via non-trusted means
        elif self.link_to_user.link_status != LoyaltyCardStatus.ACTIVE:
            self.link_to_user.link_status = LoyaltyCardStatus.ACTIVE
            commit = True

        if not (existing_card.link_date or existing_card.join_date):
            existing_card.link_date = arrow.utcnow().isoformat()
            commit = True

        if commit:
            self.db_session.commit()

        return created

    def _route_add_and_authorise(self) -> bool:
        # Handles ADD AND AUTH behaviour in the case of existing Loyalty Card <> User links

        # a link exists to *this* user (Single Wallet Scenario)
        if self.link_to_user:
            if self.link_to_user.link_status in LoyaltyCardStatus.AUTH_IN_PROGRESS:
                created = False
            elif self.link_to_user.link_status == LoyaltyCardStatus.ACTIVE:
                existing_creds = False
                if not self.link_to_user.authorised:
                    existing_creds, _ = self.check_auth_credentials_against_existing()

                if self.link_to_user.authorised or existing_creds:
                    raise falcon.HTTPConflict(
                        code="ALREADY_AUTHORISED",
                        title="Card already authorised. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to modify"
                        " authorisation credentials.",
                    )
                api_logger.error("Card status is ACTIVE but no auth credentials found!")
                raise falcon.HTTPInternalServerError
            else:
                # All other cases where user is already linked to this account
                raise falcon.HTTPConflict(
                    code="ALREADY_ADDED",
                    title="Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to authorise this "
                    "card.",
                )
        # a link exists to *a different* user ( Multi-wallet Scenario)
        else:
            self.link_account_to_user()
            # Although no account has actually been created, a new link to this user has, and we need to return a 202
            # and signal hermes to pick this up and auth.
            created = True

        return created

    def _route_add_and_register(self, existing_links: list) -> bool:  # noqa: ARG002
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
            else:
                raise falcon.HTTPConflict(
                    code="ALREADY_ADDED",
                    title="Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/register to register this "
                    "card.",
                )

        # a link exists to *a different* user (Multi-wallet Scenario)
        else:
            # We no longer care what state the card is in, in the other wallet. Let the merchant decide what to do
            # with the card.
            created = True
            self.link_account_to_user(link_status=LoyaltyCardStatus.PENDING)
        return created

    @staticmethod
    def _generate_card_number_from_barcode(loyalty_plan: Scheme, barcode: str) -> str | None:
        try:
            regex_match = re.search(loyalty_plan.card_number_regex, barcode)
            if regex_match:
                return loyalty_plan.card_number_prefix + regex_match.group(1)
        except (sre_constants.error, ValueError):
            api_logger.warning("Failed to convert barcode to card_number")

        return None

    @staticmethod
    def _generate_barcode_from_card_number(loyalty_plan: Scheme, card_number: str) -> str | None:
        try:
            regex_match = re.search(loyalty_plan.barcode_regex, card_number)
            if regex_match:
                return loyalty_plan.barcode_prefix + regex_match.group(1)
        except (sre_constants.error, ValueError):
            api_logger.warning("Failed to convert card_number to barcode")

        return None

    def _get_card_number_and_barcode(self) -> tuple[str | None, str | None]:
        """Search valid_credentials for card_number or barcode types. If either is missing, and there is a regex
        pattern available to generate it, then generate and pass back."""

        barcode: str | None = None
        card_number: str | None = None

        loyalty_plan: Scheme = self.loyalty_plan

        for _key, cred in self.valid_credentials.items():
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
        link_date = None  # Only for trusted channel

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
            merchant_identifier = next(
                item["value"] for item in self.merchant_fields if item["credential_slug"] == MERCHANT_IDENTIFIER
            )
            link_date = arrow.utcnow().isoformat()

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
            link_date=link_date,
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
            scheme_account_id=self.card_id,
            user_id=self.user_id,
            link_status=link_status,
            authorised=link_status == LoyaltyCardStatus.ACTIVE,
        )

        self.db_session.add(user_association_object)
        try:
            # Commits new loyalty card (if appropriate), as well as link to user.
            self.db_session.commit()
        except IntegrityError:
            api_logger.error(
                f"Failed to link Loyalty Card {self.card_id} with User Account {self.user_id}: Integrity Error"
            )
            raise ValidationError from None
        except DatabaseError:
            api_logger.error(
                f"Failed to link Loyalty Card {self.card_id} with User Account {self.user_id}: Database Error"
            )
            raise falcon.HTTPInternalServerError from None

        self.link_to_user = user_association_object

    def _hermes_messaging_data(self) -> dict:
        return {
            "loyalty_plan_id": self.loyalty_plan_id,
            "loyalty_card_id": self.card_id,
            "entry_id": self.link_to_user.id,  # type: ignore [union-attr]
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

import re
import sre_constants
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

import falcon
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.api.exceptions import CredentialError, ResourceNotFoundError, ValidationError
from app.api.helpers.vault import AESKeyNames
from app.handlers.base import BaseHandler
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
from app.lib.credentials import CASE_SENSITIVE_CREDENTIALS, ENCRYPTED_CREDENTIALS
from app.lib.encryption import AESCipher
from app.lib.loyalty_card import LoyaltyCardStatus
from app.messaging.sender import send_message_to_hermes
from app.report import api_logger

ADD = "ADD"
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

    Further clarifications:
        :param self.primary_auth: used in auth or add_and_auth journeys to indicate that the requesting user has
        demonstrated the necessary authority to make changes to the loyalty card including setting auth credentials and
        changing status (i.e. is not secondary to another authorised user). This includes the right to alter credentials
        , as well as trigger re-authorisations with the merchant.

    """

    journey: str
    all_answer_fields: dict = None
    loyalty_plan_id: int = None
    loyalty_plan: Scheme = None
    add_fields: list = None
    auth_fields: list = None
    register_fields: list = None
    join_fields: list = None
    valid_credentials: dict = None
    key_credential: dict = None
    all_consents: list = None
    link_to_user: SchemeAccountUserAssociation = None
    card_id: int = None
    card: SchemeAccount = None
    plan_credential_questions: dict[CredentialClass, dict[QuestionType, SchemeCredentialQuestion]] = None
    plan_consent_questions: list[Consent] = None
    primary_auth: bool = True

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

    def handle_add_only_card(self) -> bool:
        # Note ADD only is for store cards - Hermes does not need to link these so no need to call hermes.
        created = self.add_or_link_card()
        return created

    def handle_add_auth_card(self) -> bool:
        send_to_hermes = self.add_or_link_card(validate_consents=True)
        if send_to_hermes:
            self.send_to_hermes_auth()
        return send_to_hermes

    def handle_add_register_card(self) -> bool:
        send_to_hermes = self.add_or_link_card(validate_consents=True)
        if send_to_hermes:
            api_logger.info("Sending to Hermes for onward journey")
            hermes_message = self._hermes_messaging_data()
            hermes_message["register_fields"] = deepcopy(self.register_fields)
            hermes_message["consents"] = deepcopy(self.all_consents)
            send_message_to_hermes("loyalty_card_register", hermes_message)
        return send_to_hermes

    def handle_authorise_card(self) -> bool:
        send_to_hermes = False

        self.fetch_and_check_existing_card_links()
        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials()
        self.validate_and_refactor_consents()
        existing_creds, matching_creds = self.check_auth_credentials_against_existing()

        # If the requesting user is the primary auth, and has matched their own existing credentials, don't send to
        # Hermes.
        if not (self.primary_auth and existing_creds and matching_creds):
            send_to_hermes = True
            self.send_to_hermes_auth()

        return send_to_hermes

    def handle_register_card(self) -> bool:
        send_to_hermes = False

        self.fetch_and_check_existing_card_links()
        self.retrieve_plan_questions_and_answer_fields()
        self.validate_all_credentials()
        self.validate_and_refactor_consents()

        # If the requesting user is the primary auth, and the card is Registration in progress, don't send to
        # Hermes.
        if not (self.primary_auth and self.card.status in LoyaltyCardStatus.REGISTRATION_IN_PROGRESS):
            send_to_hermes = True

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

    def handle_delete_card(self) -> None:
        existing_card_link = self.fetch_and_check_single_card_user_link()

        if existing_card_link.scheme_account.status == LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS:
            raise falcon.HTTPConflict(
                code="JOIN_IN_PROGRESS", title="Loyalty card cannot be deleted until the Join process has completed"
            )

        hermes_message = self._hermes_messaging_data()
        send_message_to_hermes("delete_loyalty_card", hermes_message)

    def add_or_link_card(self, validate_consents=False):
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
        elif len(existing_card_links) > 1:
            raise falcon.HTTPInternalServerError(
                title=f"Multiple card-user relationships found for card_id " f"{self.card_id} > user_id {self.user_id}"
            )
        return existing_card_links[0].SchemeAccountUserAssociation

    def get_existing_card_links(self, only_this_user=False) -> dict:
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

        self.fetch_and_check_existing_card_links()

        if (
            len(link_objects) > 1
            and self.link_to_user.auth_provided is False
            and self.card.status is not LoyaltyCardStatus.WALLET_ONLY
            # If card already exists in multiple wallets, user is ap=False and card status is anything but
            # WALLET_ONLY, we assume that another user is primary_auth.
        ):
            self.primary_auth = False

        if self.journey == REGISTER:
            self.register_journey_additional_checks()

    def register_journey_additional_checks(self) -> None:

        if self.card.status == LoyaltyCardStatus.WALLET_ONLY:
            return

        elif self.card.status == LoyaltyCardStatus.ACTIVE:
            raise falcon.HTTPConflict(
                code="ALREADY_REGISTERED",
                title="Card is already registered. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to add this card "
                "to your wallet, or to update authorisation credentials.",
            )

        elif self.card.status == LoyaltyCardStatus.REGISTRATION_IN_PROGRESS:
            if self.primary_auth:
                return
            else:
                raise falcon.HTTPConflict(
                    code="REGISTRATION_ALREADY_IN_PROGRESS",
                    title="Card cannot be registered at this time - an existing registration is still in progress in "
                    "another wallet",
                )

        else:
            # Catch-all for other statuses
            raise falcon.HTTPConflict(code="REGISTRATION_ERROR", title="Card cannot be registered at this time.")



    def get_existing_auth_answers(self) -> dict:
        query = (
            select(SchemeAccountCredentialAnswer, SchemeCredentialQuestion)
            .join(SchemeCredentialQuestion)
            .where(
                SchemeAccountCredentialAnswer.scheme_account_id == self.card_id,
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
                    SchemeChannelAssociation.status == 0,
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

    def validate_all_credentials(self) -> None:
        """Cross-checks available plan questions with provided answers.
        Then populates a final list of validated credentials."""

        self.valid_credentials = {}

        # Validates credentials per credential class.
        # No need to relate this to with journey type - this is done in request validation.
        if self.add_fields:
            self._validate_credentials_by_class(self.add_fields, CredentialClass.ADD_FIELD)
        if self.auth_fields:
            self._validate_credentials_by_class(self.auth_fields, CredentialClass.AUTH_FIELD, require_all=True)
        if self.register_fields:
            self._validate_credentials_by_class(self.register_fields, CredentialClass.REGISTER_FIELD, require_all=True)
        if self.join_fields:
            self._validate_credentials_by_class(self.join_fields, CredentialClass.JOIN_FIELD, require_all=True)

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

    def _validate_credentials_by_class(
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

    def link_user_to_existing_or_create(self) -> bool:

        if self.journey == JOIN:
            existing_objects = []
        else:
            existing_objects = self._get_existing_objects_by_key_cred()

        created = self._route_journeys(existing_objects)
        return created

    def _get_existing_objects_by_key_cred(self):

        if self.key_credential["credential_type"] in [QuestionType.CARD_NUMBER, QuestionType.BARCODE]:
            key_credential_field = self.key_credential["credential_type"]
        else:
            key_credential_field = "main_answer"

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

    def _route_journeys(self, existing_objects: list) -> bool:

        created = False

        existing_scheme_account_ids = []

        for item in existing_objects:
            existing_scheme_account_ids.append(item.SchemeAccount.id)

        number_of_existing_accounts = len(set(existing_scheme_account_ids))

        if number_of_existing_accounts == 0:
            self.create_new_loyalty_card()
            created = True
        elif number_of_existing_accounts == 1:

            self.card_id = existing_scheme_account_ids[0]
            api_logger.info(f"Existing loyalty card found: {self.card_id}")

            existing_card = existing_objects[0].SchemeAccount
            existing_links = list({item.SchemeAccountUserAssociation for item in existing_objects})

            user_link = None
            for link in existing_links:
                if link.user_id == self.user_id:
                    user_link = link

            if self.journey == ADD_AND_REGISTER:
                created = self._route_add_and_register(existing_card, user_link, created)

            elif self.journey == ADD_AND_AUTHORISE:
                created = self._route_add_and_authorise(existing_card, user_link, created)

            elif not user_link:
                self.link_account_to_user()

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

        if not self.primary_auth and not all_match:
            raise CredentialError

        existing_credentials = True if existing_auths else False
        return existing_credentials, all_match

    def _route_add_and_authorise(
        self, existing_card: SchemeAccount, user_link: SchemeAccountUserAssociation, created: bool
    ) -> bool:
        # Handles ADD AND AUTH behaviour in the case of existing Loyalty Card <> User links
        # Only acceptable route is if the existing account is in another wallet, and credentials match those we have
        # stored (if any)

        if existing_card.status in LoyaltyCardStatus.AUTH_IN_PROGRESS:
            created = False

        elif user_link:

            if existing_card.status == LoyaltyCardStatus.ACTIVE and user_link.auth_provided is True:
                # Only 1 link, which is for this user, card is ACTIVE and this user has authed already
                self.primary_auth = True
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

        else:
            # There are 1 or more links, belongs to one or more people but NOT this user
            if not existing_card.status == LoyaltyCardStatus.WALLET_ONLY:
                # If the existing card is anything but Wallet only, we don't re-authorise in hermes.
                self.primary_auth = False

            self.check_auth_credentials_against_existing()
            self.link_account_to_user()
            # Although no account has actually been created, a new link to this user has, and we need to return a 202
            # and signal hermes to pick this up.
            created = True

        return created

    def _route_add_and_register(
        self, existing_card: SchemeAccount, user_link: SchemeAccountUserAssociation, created: bool
    ) -> bool:
        # Handles ADD_AND_REGISTER behaviour in the case of existing Loyalty Card <> User links

        if existing_card.status == LoyaltyCardStatus.ACTIVE:
            raise falcon.HTTPConflict(code="ALREADY_REGISTERED", title="Card is already registered")

        # Single Wallet
        if user_link:
            if existing_card.status in LoyaltyCardStatus.REGISTRATION_IN_PROGRESS:
                created = False
            else:
                raise falcon.HTTPConflict(
                    code="ALREADY_ADDED",
                    title="Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/register to register this "
                    "card.",
                )

        # Multi-wallet
        else:
            if existing_card.status in LoyaltyCardStatus.REGISTRATION_IN_PROGRESS:
                raise falcon.HTTPConflict(
                    code="REGISTRATION_ALREADY_IN_PROGRESS",
                    title="Card cannot be registered at this time - an existing registration is still in progress in "
                    "another wallet.",
                )
            elif existing_card.status == LoyaltyCardStatus.WALLET_ONLY:
                created = True
                self.link_account_to_user()
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

    def _get_card_number_and_barcode(self) -> (str, str):
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

        if self.journey == ADD:
            new_status = LoyaltyCardStatus.WALLET_ONLY
        elif self.journey == JOIN:
            new_status = LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS
        else:
            new_status = LoyaltyCardStatus.PENDING

        main_answer = self.key_credential["credential_answer"] if self.key_credential else ""

        loyalty_card = SchemeAccount(
            status=new_status,
            order=1,
            created=datetime.now(),
            updated=datetime.now(),
            card_number=card_number or "",
            barcode=barcode or "",
            main_answer=main_answer,
            scheme_id=self.loyalty_plan_id,
            is_deleted=False,
            balances={},
            vouchers={},
            transactions=[],
            pll_links=[],
            formatted_images={},
        )

        self.db_session.add(loyalty_card)
        self.db_session.flush()

        self.card_id = loyalty_card.id

        self.add_credential_answers_to_db_session()

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

    def add_credential_answers_to_db_session(self) -> None:

        answers_to_add = []
        for key, cred in self.valid_credentials.items():
            # We only store ADD credentials in the database from Angelia. Auth fields (including register/auth fields)
            # are checked again and stored by hermes.
            if cred["credential_class"] == CredentialClass.ADD_FIELD:
                # Todo: Will leave this in as a precaution but we may want to remove later
                #  - add fields are never encrypted(?)
                if key in ENCRYPTED_CREDENTIALS:
                    cred["credential_answer"] = (
                        AESCipher(AESKeyNames.LOCAL_AES_KEY).encrypt(cred["credential_answer"]).decode("utf-8")
                    )

                answers_to_add.append(
                    SchemeAccountCredentialAnswer(
                        scheme_account_id=self.card_id,
                        question_id=cred["credential_question_id"],
                        answer=cred["credential_answer"],
                    )
                )

        self.db_session.bulk_save_objects(answers_to_add)

    def link_account_to_user(self) -> None:
        # need to add in status for wallet only
        api_logger.info(f"Linking Loyalty Card {self.card_id} to User Account {self.user_id}")
        auth_provided = True
        if self.journey == ADD:
            auth_provided = False
        user_association_object = SchemeAccountUserAssociation(
            scheme_account_id=self.card_id, user_id=self.user_id, auth_provided=auth_provided
        )

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

    def _hermes_messaging_data(self) -> dict:
        return {
            "loyalty_plan_id": self.loyalty_plan_id,
            "loyalty_card_id": self.card_id,
            "user_id": self.user_id,
            "channel": self.channel_id,
            "journey": self.journey,
            "auto_link": True,
        }

    def send_to_hermes_auth(self) -> None:
        api_logger.info("Sending to Hermes for onward authorisation")
        hermes_message = self._hermes_messaging_data()
        hermes_message["primary_auth"] = self.primary_auth
        hermes_message["authorise_fields"] = deepcopy(self.auth_fields)
        hermes_message["consents"] = deepcopy(self.all_consents)

        send_message_to_hermes("loyalty_card_authorise", hermes_message)

from dataclasses import dataclass
from enum import Enum

import falcon
from sqlalchemy.exc import DatabaseError
from sqlalchemy.sql.expression import select

from app.handlers.base import BaseHandler
from app.hermes.models import (
    Channel,
    ClientApplication,
    Consent,
    Scheme,
    SchemeChannelAssociation,
    SchemeCredentialQuestion,
    SchemeDocument,
    ThirdPartyConsentLink,
)
from app.lib.credentials import ANSWER_TYPE_CHOICES
from app.report import api_logger


class DocumentClass(str, Enum):
    ENROL = "ENROL"
    REGISTER = "REGISTRATION"
    ADD = "ADD"
    AUTHORISE = "AUTHORISE"


class CredentialClass(str, Enum):
    ADD_FIELD = "add_field"
    AUTH_FIELD = "auth_field"
    JOIN_FIELD = "enrol_field"  # API naming convention does not yet match db level field name
    REGISTER_FIELD = "register_field"


class ConsentJourney(str, Enum):
    pass


@dataclass
class LoyaltyPlanHandler(BaseHandler):

    loyalty_plan_id: int
    loyalty_plan: Scheme = None
    loyalty_plan_credentials: dict = None
    consents: dict = None
    documents: dict = None

    def get_journey_fields(self):
        self.fetch_loyalty_plan_and_information()
        self.fetch_consents()
        return self.create_response_data()

    def fetch_loyalty_plan_and_information(self):
        # Fetches Loyalty Plan (if exists), associated Credential Questions,
        # Plan Documents (if any) and Consents (if any)

        query = (
            select(Scheme, SchemeCredentialQuestion, SchemeDocument)
            .join(SchemeCredentialQuestion)
            .join(SchemeChannelAssociation)
            .join(Channel)
            .join(SchemeDocument, isouter=True)
            .filter(Scheme.id == self.loyalty_plan_id)
            .filter(Channel.bundle_id == self.channel_id)
            .order_by(SchemeCredentialQuestion.order)
        )

        try:
            plan_information = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        if not plan_information:
            api_logger.error("No loyalty plan information/credentials returned")
            raise falcon.HTTPNotFound
            pass

        schemes, creds, docs = list(zip(*plan_information))

        self.loyalty_plan = schemes[0]

        self.loyalty_plan_credentials = {}

        # Removes duplicates but preserves order
        all_creds = list(dict.fromkeys(creds))
        all_documents = list(dict.fromkeys(docs))

        self.categorise_creds_and_documents_to_class(all_creds, all_documents)

    def categorise_creds_and_documents_to_class(self, all_credentials: list, all_documents: list):
        # Categorises creds by class
        self.loyalty_plan_credentials = {}
        for cred_class in CredentialClass:
            self.loyalty_plan_credentials[cred_class] = []
            for item in all_credentials:
                if getattr(item, cred_class):
                    self.loyalty_plan_credentials[cred_class].append(item)

        # Removes nulls (if no docs) and categorises docs by class
        self.documents = {}
        for doc_class in DocumentClass:
            self.documents[doc_class] = []
            for document in all_documents:
                if document:
                    if doc_class in document.display:
                        self.documents[doc_class].append(document)

    def fetch_consents(self):
        query = (
            select(Consent, ThirdPartyConsentLink)
            .join(ThirdPartyConsentLink)
            .join(ClientApplication)
            .join(Channel)
            .filter(ThirdPartyConsentLink.scheme_id == self.loyalty_plan_id)
            .filter(Channel.bundle_id == self.channel_id)
            .order_by(Consent.order)
        )

        try:
            consents = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        self.consents = {}
        for cred_class in CredentialClass:
            self.consents[cred_class] = []
            for consent in consents:
                if getattr(consent.ThirdPartyConsentLink, cred_class):
                    self.consents[cred_class].append(consent.Consent)

    def create_response_data(self) -> dict:
        def _consents_to_dict(consents: list[Consent]) -> list[dict]:
            consents_list = []
            for consent in consents:
                consent_detail = {
                    "order": consent.order,
                    "name": consent.slug,
                    "is_acceptance_required": consent.required,
                    "description": consent.text,
                }
                consents_list.append(consent_detail)

            return consents_list

        def _documents_to_dict(documents: list[SchemeDocument]) -> list[dict]:
            docs_list = []
            for document in documents:
                docs_list.append({"name": document.name, "url": document.url, "description": document.description})

            return docs_list

        def _credentials_to_dict(credentials: list[SchemeCredentialQuestion]) -> list[dict]:
            creds_list = []
            for cred in credentials:
                cred_detail = {
                    "order": cred.order,
                    "display_label": cred.label,
                    "validation": cred.validation,
                    "description": cred.description,
                    "credential_slug": cred.type,
                    "type": ANSWER_TYPE_CHOICES[cred.answer_type],
                    "is_sensitive": True if cred.answer_type == 1 else False,
                }

                if cred.choice:
                    cred_detail["choice"] = cred.choice

                creds_list.append(cred_detail)

            return creds_list

        def _get_all_fields(field_class) -> dict:

            field_class_response = {}

            # To convert from Credential classes to Document classes
            cred_to_doc_key = {
                CredentialClass.AUTH_FIELD: DocumentClass.AUTHORISE,
                CredentialClass.ADD_FIELD: DocumentClass.ADD,
                CredentialClass.REGISTER_FIELD: DocumentClass.REGISTER,
                CredentialClass.JOIN_FIELD: DocumentClass.ENROL,
            }

            if self.loyalty_plan_credentials[field_class]:
                field_class_response["credentials"] = _credentials_to_dict(self.loyalty_plan_credentials[field_class])
            if self.documents[cred_to_doc_key[field_class]]:
                field_class_response["plan_documents"] = _documents_to_dict(
                    self.documents[cred_to_doc_key[field_class]]
                )
            if self.consents[field_class]:
                field_class_response["consents"] = _consents_to_dict(self.consents[field_class])
            # add consents

            return field_class_response

        response = {
            "id": self.loyalty_plan_id,
            "join_fields": _get_all_fields(CredentialClass.JOIN_FIELD),
            "register_ghost_card_fields": _get_all_fields(CredentialClass.REGISTER_FIELD),
            "add_fields": _get_all_fields(CredentialClass.ADD_FIELD),
            "authorise_fields": _get_all_fields(CredentialClass.AUTH_FIELD),
        }

        # Strips out empty keys from final response
        clean_response = {key: value for key, value in response.items() if value}

        return clean_response
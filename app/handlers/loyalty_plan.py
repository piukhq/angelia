from dataclasses import dataclass
from enum import Enum
from operator import attrgetter
from typing import Iterable, Optional, Type, Union

import falcon
from sqlalchemy.exc import DatabaseError
from sqlalchemy.sql.expression import select

import settings
from app.api.exceptions import ResourceNotFoundError
from app.handlers.base import BaseHandler
from app.hermes.models import (
    Channel,
    ClientApplication,
    Consent,
    Scheme,
    SchemeChannelAssociation,
    SchemeContent,
    SchemeCredentialQuestion,
    SchemeDetail,
    SchemeDocument,
    SchemeImage,
    ThirdPartyConsentLink,
)
from app.lib.credentials import ANSWER_TYPE_CHOICES
from app.lib.loyalty_plan import SchemeTier
from app.report import api_logger


class LoyaltyPlanJourney(str, Enum):
    ADD = "ADD"
    AUTHORISE = "AUTHORISE"
    JOIN = "JOIN"
    REGISTER = "REGISTER"


class CredentialField(str, Enum):
    ADD_FIELD = "add_fields"
    AUTH_FIELD = "authorise_fields"
    JOIN_FIELD = "join_fields"
    REGISTER_FIELD = "register_ghost_card_fields"


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
    manual_question: SchemeCredentialQuestion = None
    scan_question: SchemeCredentialQuestion = None

    def get_journey_fields(self, scheme=None, creds=None, docs=None, consents=None) -> dict:
        if not all([scheme, creds, docs]):
            schemes, creds, docs = self.fetch_loyalty_plan_and_information()
            scheme = schemes[0]

        self.loyalty_plan = scheme
        self.loyalty_plan_credentials = {}
        self._categorise_creds_and_docs(creds, docs)

        if consents is None:
            consents = self.fetch_consents()

        self._categorise_consents(consents)

        return self._format_journey_fields()

    def fetch_loyalty_plan_and_information(
        self,
    ):
        # Fetches Loyalty Plan (if exists), associated Credential Questions,
        # Plan Documents (if any) and Consents (if any)

        query = (
            select(Scheme, SchemeCredentialQuestion, SchemeDocument)
            .join(SchemeCredentialQuestion)
            .join(SchemeChannelAssociation)
            .join(Channel)
            .join(SchemeDocument, isouter=True)
            .filter(Scheme.id == self.loyalty_plan_id, Channel.bundle_id == self.channel_id)
            .order_by(SchemeCredentialQuestion.order)
        )

        try:
            plan_information = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        if not plan_information:
            api_logger.error("No loyalty plan information/credentials returned")
            raise ResourceNotFoundError

        schemes, creds, docs = list(zip(*plan_information))

        return schemes, creds, docs

    def _categorise_creds_and_docs(self, credentials, documents):
        # Removes duplicates but preserves order
        all_creds = list(dict.fromkeys(credentials))
        all_documents = list(dict.fromkeys(documents))

        categorised_creds = self.categorise_creds_by_class(all_creds)
        categorised_docs = self.categorise_documents_to_class(all_documents)

        return categorised_creds, categorised_docs

    def _categorise_consents(
        self, consents: list[Union[tuple[Type[Consent], Type[ThirdPartyConsentLink]], ThirdPartyConsentLink]]
    ) -> None:
        self.consents = {}

        if consents and isinstance(consents[0], ThirdPartyConsentLink):
            for cred_class in CredentialClass:
                self.consents[cred_class] = []
                for consent in consents:
                    if getattr(consent, cred_class):
                        self.consents[cred_class].append(consent.consent)
        else:
            for cred_class in CredentialClass:
                self.consents[cred_class] = []
                for consent in consents:
                    if getattr(consent.ThirdPartyConsentLink, cred_class):
                        self.consents[cred_class].append(consent.Consent)

    def categorise_creds_by_class(self, all_credentials: list):
        """
        In Angelia, register and join fields are not defined as those credential questions marked as such in the db.
        Rather, 'register_fields' (for example) should represent all fields necessary to complete the register journey.
        This means that in the case of register fields, we should return all fields marked as register fields in the db
        as well as the manual and/or scan question(s) required for this journey (usually an add field). Therefore,
        card_number, for example, will be returned as a register_ghost_card_field, even though it is
        not marked as such in the db.
        """

        # Finds manual and scan questions:
        for cred in all_credentials:
            if getattr(cred, "manual_question"):
                self.manual_question = cred
            if getattr(cred, "scan_question"):
                self.scan_question = cred

        # - if the scheme has a scan question and a manual question, do not include the manual question - (this
        # will be subordinated to the scan question later)
        if self.manual_question and self.scan_question:
            all_credentials.remove(self.manual_question)

        # Categorises credentials by class
        self.loyalty_plan_credentials = {}
        for cred_class in CredentialClass:
            self.loyalty_plan_credentials[cred_class] = []
            for item in all_credentials:
                if getattr(item, cred_class):
                    self.loyalty_plan_credentials[cred_class].append(item)

        return self.loyalty_plan_credentials

    def categorise_documents_to_class(self, all_documents: list):
        # Removes nulls (if no docs) and categorises docs by class
        self.documents = {}
        for doc_class in DocumentClass:
            self.documents[doc_class] = []
            for document in all_documents:
                if document and doc_class in document.display:
                    self.documents[doc_class].append(document)
        # todo: sort documents by order field here when implemented
        return self.documents

    def fetch_consents(self):
        query = (
            select(Consent, ThirdPartyConsentLink)
            .join(ThirdPartyConsentLink)
            .join(ClientApplication)
            .join(Channel)
            .filter(ThirdPartyConsentLink.scheme_id == self.loyalty_plan_id, Channel.bundle_id == self.channel_id)
            .order_by(Consent.order)
        )

        try:
            return self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch consent records from database")
            raise falcon.HTTPInternalServerError

    def _format_journey_fields(self) -> dict:
        return {
            "join_fields": self._get_all_fields(CredentialClass.JOIN_FIELD),
            "register_ghost_card_fields": self._get_all_fields(CredentialClass.REGISTER_FIELD),
            "add_fields": self._get_all_fields(CredentialClass.ADD_FIELD),
            "authorise_fields": self._get_all_fields(CredentialClass.AUTH_FIELD),
        }

    @staticmethod
    def _consents_to_dict(consents: list[Consent]) -> list[dict]:
        return [
            {
                "order": consent.order,
                "consent_slug": consent.slug,
                "is_acceptance_required": consent.required,
                "description": consent.text,
            }
            for consent in consents
        ]

    @staticmethod
    def _documents_to_dict(documents: list[SchemeDocument]) -> list[dict]:
        return [
            {
                "order": document.order,
                "name": document.name,
                "url": document.url,
                "description": document.description,
                "is_acceptance_required": document.checkbox,
            }
            for document in documents
        ]

    @staticmethod
    def _credential_to_dict(cred: SchemeCredentialQuestion) -> dict:
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

        return cred_detail

    def _credentials_to_dict(self, credentials: list[SchemeCredentialQuestion]) -> list[dict]:
        creds_list = []
        for cred in credentials:
            cred_detail = self._credential_to_dict(cred)

            # Subordinates the manual question to scan question and equates their order
            if cred == self.scan_question and self.manual_question:
                cred_detail["alternative"] = self._credential_to_dict(self.manual_question)
                cred_detail["alternative"]["order"] = self.scan_question.order

            creds_list.append(cred_detail)

        return creds_list

    def _get_all_fields(self, field_class) -> dict:
        field_class_response = {}

        # To convert from Credential classes to Document classes
        cred_to_doc_key = {
            CredentialClass.AUTH_FIELD: DocumentClass.AUTHORISE,
            CredentialClass.ADD_FIELD: DocumentClass.ADD,
            CredentialClass.REGISTER_FIELD: DocumentClass.REGISTER,
            CredentialClass.JOIN_FIELD: DocumentClass.ENROL,
        }

        if self.loyalty_plan_credentials[field_class]:
            field_class_response["credentials"] = self._credentials_to_dict(self.loyalty_plan_credentials[field_class])
        if self.documents[cred_to_doc_key[field_class]]:
            field_class_response["plan_documents"] = self._documents_to_dict(
                self.documents[cred_to_doc_key[field_class]]
            )
        if self.consents[field_class]:
            field_class_response["consents"] = self._consents_to_dict(self.consents[field_class])
        # add consents

        return field_class_response


class LoyaltyPlansHandler(BaseHandler):
    def _fetch_all_plan_information(
        self,
    ) -> tuple[
        Scheme,
        SchemeCredentialQuestion,
        SchemeDocument,
        SchemeImage,
        ThirdPartyConsentLink,
        SchemeDetail,
        SchemeContent,
    ]:
        query = (
            select(
                Scheme,
                SchemeCredentialQuestion,
                SchemeDocument,
                SchemeImage,
                ThirdPartyConsentLink,
                SchemeDetail,
                SchemeContent,
            )
            .join(SchemeCredentialQuestion, SchemeCredentialQuestion.scheme_id == Scheme.id)
            .join(SchemeChannelAssociation, SchemeChannelAssociation.scheme_id == Scheme.id)
            .join(Channel, Channel.id == SchemeChannelAssociation.bundle_id)
            .join(SchemeDocument, SchemeDocument.scheme_id == Scheme.id, isouter=True)
            .join(SchemeImage, SchemeImage.scheme_id == Scheme.id, isouter=True)
            .join(ThirdPartyConsentLink, ThirdPartyConsentLink.client_app_id == Channel.client_id, isouter=True)
            .join(SchemeDetail, SchemeDetail.scheme_id_id == Scheme.id, isouter=True)
            .join(SchemeContent, SchemeContent.scheme_id == Scheme.id, isouter=True)
            .where(Channel.bundle_id == self.channel_id)
        )

        try:
            return self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.exception("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

    @staticmethod
    def _format_images(images: Iterable[SchemeImage]) -> list:
        def get_encoding(obj: SchemeImage) -> Optional[str]:
            if obj.encoding:
                return obj.encoding

            try:
                return obj.image.split(".")[-1].replace("/", "")
            except (IndexError, AttributeError):
                return None

        return [
            {
                "id": image.id,
                "type": image.image_type_code,
                "url": f"{settings.MEDIA_ROOT}{image.image}",
                "description": image.description,
                "encoding": get_encoding(image),
            }
            for image in images
        ]

    @staticmethod
    def _format_tiers(tiers: Iterable[SchemeDetail]) -> list:
        return [
            {
                "name": tier.name,
                "description": tier.description,
            }
            for tier in tiers
        ]

    @staticmethod
    def _format_contents(contents: Iterable[SchemeContent]) -> list:
        return [
            {
                "column": content.column,
                "value": content.value,
            }
            for content in contents
        ]

    @staticmethod
    def _get_plan_type(plan: Scheme) -> int:
        if plan.tier == SchemeTier.COMING_SOON:
            plan_type = 3
        elif plan.tier == SchemeTier.PLL:
            plan_type = 2
        elif plan.has_points or plan.has_transactions:
            plan_type = 1
        else:
            plan_type = 0

        return plan_type

    @staticmethod
    def _get_journeys(journey_fields: dict) -> list:
        journey_to_type = {
            LoyaltyPlanJourney.ADD: 0,
            LoyaltyPlanJourney.AUTHORISE: 1,
            LoyaltyPlanJourney.REGISTER: 2,
            LoyaltyPlanJourney.JOIN: 3,
        }

        cred_class_to_journey = {
            CredentialField.AUTH_FIELD: LoyaltyPlanJourney.AUTHORISE,
            CredentialField.REGISTER_FIELD: LoyaltyPlanJourney.REGISTER,
            CredentialField.JOIN_FIELD: LoyaltyPlanJourney.JOIN,
        }

        # All plans should support ADD journey
        journeys = [{"type": journey_to_type[LoyaltyPlanJourney.ADD], "description": LoyaltyPlanJourney.ADD}]

        for field_type in cred_class_to_journey:
            if journey_fields.get(field_type):
                journey = cred_class_to_journey[field_type]
                journeys.append({"type": journey_to_type[journey], "description": journey})

        return journeys

    def _format_plan_data(
        self,
        plan: "Scheme",
        images: Iterable[SchemeImage],
        tiers: Iterable[SchemeDetail],
        journey_fields: dict,
        contents: Iterable[SchemeContent],
    ) -> dict:
        images = self._format_images(images)
        tiers = self._format_tiers(tiers)
        content = self._format_contents(contents)

        plan_type = self._get_plan_type(plan)
        journeys = self._get_journeys(journey_fields)
        return {
            "loyalty_plan_id": plan.id,
            "plan_popularity": plan.plan_popularity,
            "plan_features": {
                "has_points": plan.has_points,
                "has_transactions": plan.has_transactions,
                "plan_type": plan_type,
                "barcode_type": plan.barcode_type,
                "colour": plan.colour,
                "journeys": journeys,
            },
            "images": images,
            "plan_details": {
                "company_name": plan.company,
                "plan_name": plan.plan_name,
                "plan_label": plan.plan_name_card,
                "plan_url": plan.url,
                "plan_summary": plan.plan_summary,
                "plan_description": plan.plan_description,
                "redeem_instructions": plan.barcode_redeem_instructions,
                "plan_register_info": plan.plan_register_info,
                "join_incentive": plan.enrol_incentive,
                "category": plan.category.name,
                "tiers": tiers,
            },
            "journey_fields": journey_fields,
            "content": content,
        }

    @staticmethod
    def _sort_by_attr(
        credentials: Iterable,
        attr: str = "order",
    ) -> list:
        return sorted(credentials, key=attrgetter(attr))

    def get_all_plans(self) -> list:
        plan_information = self._fetch_all_plan_information()

        # Order of fields must match the order of the select statement in self._fetch_all_plan_information()
        plan_info_fields = ("credentials", "documents", "images", "consents", "tiers", "contents")
        sorted_plan_information = {}
        for row in plan_information:
            plan = row[0]
            if plan.slug not in sorted_plan_information:
                sorted_plan_information[plan.slug] = {"plan": plan}
                sorted_plan_information[plan.slug].update({info_field: set() for info_field in plan_info_fields})

            for index, field_name in enumerate(plan_info_fields):
                result_value = row[index + 1]
                if index == plan_info_fields.index("consents"):
                    if result_value.scheme_id != plan.id:
                        result_value = None

                if result_value is not None:
                    sorted_plan_information[plan.slug][field_name].add(result_value)

        resp = []
        for plan_info in sorted_plan_information.values():
            plan_info["credentials"] = self._sort_by_attr(plan_info["credentials"])
            plan_info["consents"] = self._sort_by_attr(plan_info["consents"], attr="consent.order")
            plan_info["documents"] = self._sort_by_attr(plan_info["documents"])

            journey_fields = LoyaltyPlanHandler(
                user_id=self.user_id,
                channel_id=self.channel_id,
                db_session=self.db_session,
                loyalty_plan_id=plan_info["plan"].id,
            ).get_journey_fields(
                scheme=plan_info["plan"],
                creds=plan_info["credentials"],
                docs=plan_info["documents"],
                consents=plan_info["consents"],
            )

            resp.append(
                self._format_plan_data(
                    plan_info["plan"],
                    plan_info["images"],
                    plan_info["tiers"],
                    journey_fields,
                    plan_info["contents"],
                )
            )

        return resp

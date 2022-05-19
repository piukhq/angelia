import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from operator import attrgetter
from typing import Iterable, Optional, Union

import falcon
from sqlalchemy.engine import Row
from sqlalchemy.exc import DatabaseError
from sqlalchemy.sql.expression import and_, or_, select

import settings
from app.api.exceptions import ResourceNotFoundError
from app.handlers.base import BaseHandler
from app.hermes.models import (
    Channel,
    ClientApplication,
    Consent,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeContent,
    SchemeCredentialQuestion,
    SchemeDetail,
    SchemeDocument,
    SchemeImage,
    ThirdPartyConsentLink,
)
from app.lib.credentials import ANSWER_TYPE_CHOICES
from app.lib.images import ImageStatus, ImageTypes
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


# SchemeBundleAssociation statuses
class LoyaltyPlanChannelStatus(IntEnum):
    ACTIVE = 0
    SUSPENDED = 1
    INACTIVE = 2


class BaseLoyaltyPlanHandler:
    @staticmethod
    def _format_images(images: Iterable[SchemeImage], overview: bool = False) -> list:
        def get_encoding(obj: SchemeImage) -> Optional[str]:
            if obj.encoding:
                return obj.encoding

            try:
                return obj.image.split(".")[-1].replace("/", "")
            except (IndexError, AttributeError):
                return None

        if overview and images:
            images = filter(lambda x: x.image_type_code == 3, images)

        return [
            {
                "id": image.id,
                "type": image.image_type_code,
                "url": os.path.join(settings.CUSTOM_DOMAIN, image.image),
                "description": image.description,
                "encoding": get_encoding(image),
                "order": image.order,
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
            CredentialField.ADD_FIELD: LoyaltyPlanJourney.ADD,
            CredentialField.AUTH_FIELD: LoyaltyPlanJourney.AUTHORISE,
            CredentialField.REGISTER_FIELD: LoyaltyPlanJourney.REGISTER,
            CredentialField.JOIN_FIELD: LoyaltyPlanJourney.JOIN,
        }

        journeys = []
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
        is_in_wallet: bool,
    ) -> dict:
        images = self._format_images(images)
        tiers = self._format_tiers(tiers)
        content = self._format_contents(contents)

        plan_type = self._get_plan_type(plan)
        journeys = self._get_journeys(journey_fields)
        return {
            "loyalty_plan_id": plan.id,
            "is_in_wallet": is_in_wallet,
            "plan_popularity": plan.plan_popularity,
            "plan_features": {
                "has_points": plan.has_points,
                "has_transactions": plan.has_transactions,
                "plan_type": plan_type,
                "barcode_type": plan.barcode_type,
                "colour": plan.colour,
                "text_colour": plan.text_colour,
                "journeys": journeys,
            },
            "images": images,
            "plan_details": {
                "company_name": plan.company,
                "plan_name": plan.name,
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

    def _format_plan_data_overview(
        self,
        plan: "Scheme",
        images: Iterable[SchemeImage],
        is_in_wallet: bool,
    ) -> dict:
        images = self._format_images(images, overview=True)
        plan_type = self._get_plan_type(plan)
        return {
            "loyalty_plan_id": plan.id,
            "is_in_wallet": is_in_wallet,
            "plan_name": plan.name,
            "company_name": plan.company,
            "plan_popularity": plan.plan_popularity,
            "plan_type": plan_type,
            "colour": plan.colour,
            "text_colour": plan.text_colour,
            "category": plan.category.name,
            "images": images,
        }

    @staticmethod
    def _sort_by_attr(
        obj: Iterable,
        attr: str = "order",
    ) -> Union[Iterable, list]:
        if obj:
            return sorted(obj, key=attrgetter(attr))
        else:
            return obj

    @staticmethod
    def _init_plan_info_dict(plan_ids: list[int], plan_ids_in_wallet: set[int]) -> dict:
        sorted_plan_information = {}
        for plan_id in plan_ids:
            sorted_plan_information[plan_id] = {}
            for info_field in ("credentials", "documents", "images", "consents", "tiers", "contents"):
                sorted_plan_information[plan_id][info_field] = set()

            sorted_plan_information[plan_id]["is_in_wallet"] = plan_id in plan_ids_in_wallet

        return sorted_plan_information

    @staticmethod
    def _create_plan_and_images_dict_for_overview(plans_and_images: list[Row[Scheme, SchemeImage]]) -> dict:
        sorted_plan_information = {}

        for row in plans_and_images:
            plan = row[0]

            if plan.id not in sorted_plan_information.keys():
                sorted_plan_information.update({plan.id: {"plan": plan, "images": []}})

            if row[1]:
                sorted_plan_information[plan.id]["images"].append(row[1])

        return sorted_plan_information

    @staticmethod
    def _categorise_plan_and_credentials(plans_and_credentials: list, sorted_plan_information: dict) -> None:
        for row in plans_and_credentials:
            plan = row[0]
            if "plan" not in sorted_plan_information[plan.id]:
                sorted_plan_information[plan.id].update({"plan": plan})

            if row[1]:
                sorted_plan_information[plan.id]["credentials"].add(row[1])

    @staticmethod
    def _categorise_plan_info(plan_info: list, sorted_plan_information: dict) -> None:
        for row in plan_info:
            # 0 index of the row is plan so start=1 to offset that
            for index, field_type in enumerate(("documents", "images", "tiers", "contents"), start=1):
                if field_type == "tiers" and row[index]:
                    # The field name should be changed to scheme_id for consistency
                    sorted_plan_information[row[index].scheme_id_id][field_type].add(row[index])

                elif row[index]:
                    sorted_plan_information[row[index].scheme_id][field_type].add(row[index])

    def _sort_info_by_plan(
        self,
        plans_and_credentials: list[Row[Scheme, SchemeCredentialQuestion]],
        plan_info: list[Row[Scheme, SchemeDocument, SchemeImage, SchemeDetail, SchemeContent]],
        consents: list[Row[ThirdPartyConsentLink]],
        plan_ids_in_wallet: list[Row[int]],
    ) -> dict:
        plan_ids_in_wallet = {row[0] for row in plan_ids_in_wallet}
        plan_ids = [row[0].id for row in plans_and_credentials]
        sorted_plan_information = self._init_plan_info_dict(plan_ids, plan_ids_in_wallet)

        self._categorise_plan_and_credentials(plans_and_credentials, sorted_plan_information)
        self._categorise_plan_info(plan_info, sorted_plan_information)

        for row in consents:
            sorted_plan_information[row[0].scheme_id]["consents"].add(row[0])

        return sorted_plan_information

    @staticmethod
    def _details_sort_info_by_plan(
        scheme_details: list[Row[Scheme, SchemeImage, SchemeDetail]],
    ) -> dict:
        sorted_plan_information = {}
        for row in scheme_details:
            plan = row[0]

            if plan.id not in sorted_plan_information.keys():
                sorted_plan_information.update({plan.id: {"plan": plan, "images": set(), "tiers": set()}})

            if row[1]:
                sorted_plan_information[plan.id]["images"].add(row[1])

            if row[2]:
                sorted_plan_information[plan.id]["tiers"].add(row[2])

        return sorted_plan_information

    @property
    def select_plan_query(self):
        return (
            select(
                Scheme,
                SchemeCredentialQuestion,
            )
            .join(SchemeCredentialQuestion, SchemeCredentialQuestion.scheme_id == Scheme.id)
            .join(
                SchemeChannelAssociation,
                and_(
                    SchemeChannelAssociation.scheme_id == Scheme.id,
                    SchemeChannelAssociation.status == LoyaltyPlanChannelStatus.ACTIVE.value,
                ),
            )
            .join(Channel, Channel.id == SchemeChannelAssociation.bundle_id)
        )

    @property
    def select_plan_and_images_query(self):
        return (
            select(
                Scheme,
                SchemeImage,
            )
            .join(
                SchemeChannelAssociation,
                and_(
                    SchemeChannelAssociation.scheme_id == Scheme.id,
                    SchemeChannelAssociation.status == LoyaltyPlanChannelStatus.ACTIVE.value,
                ),
            )
            .join(Channel, Channel.id == SchemeChannelAssociation.bundle_id)
            .join(
                SchemeImage,
                and_(
                    SchemeImage.scheme_id == Scheme.id,
                    SchemeImage.start_date <= datetime.now(),
                    SchemeImage.status != ImageStatus.DRAFT,
                    SchemeImage.image_type_code == ImageTypes.ICON,
                    or_(SchemeImage.end_date.is_(None), SchemeImage.end_date >= datetime.now()),
                ),
                isouter=True,
            )
        )

    @property
    def select_plan_details_query(self):
        return (
            select(
                Scheme,
                SchemeImage,
                SchemeDetail,
            )
            .join(
                SchemeChannelAssociation,
                and_(
                    SchemeChannelAssociation.scheme_id == Scheme.id,
                    SchemeChannelAssociation.status == LoyaltyPlanChannelStatus.ACTIVE.value,
                ),
            )
            .join(Channel, Channel.id == SchemeChannelAssociation.bundle_id)
            .join(
                SchemeImage,
                and_(
                    SchemeImage.scheme_id == Scheme.id,
                    SchemeImage.start_date <= datetime.now(),
                    SchemeImage.status != ImageStatus.DRAFT,
                    SchemeImage.image_type_code == ImageTypes.ICON,
                    or_(SchemeImage.end_date.is_(None), SchemeImage.end_date >= datetime.now()),
                ),
                isouter=True,
            )
            .join(SchemeDetail, SchemeDetail.scheme_id_id == Scheme.id, isouter=True)
        )

    @property
    def select_scheme_info_query(self):
        return (
            select(
                Scheme.id,
                SchemeDocument,
                SchemeImage,
                SchemeDetail,
                SchemeContent,
            )
            .join(SchemeDocument, SchemeDocument.scheme_id == Scheme.id, isouter=True)
            .join(
                SchemeImage,
                and_(
                    SchemeImage.scheme_id == Scheme.id,
                    SchemeImage.start_date <= datetime.now(),
                    SchemeImage.status != ImageStatus.DRAFT,
                    or_(SchemeImage.end_date.is_(None), SchemeImage.end_date >= datetime.now()),
                ),
                isouter=True,
            )
            .join(SchemeDetail, SchemeDetail.scheme_id_id == Scheme.id, isouter=True)
            .join(SchemeContent, SchemeContent.scheme_id == Scheme.id, isouter=True)
        )

    @property
    def select_consents_query(self):
        return (
            select(ThirdPartyConsentLink)
            .join(Channel, Channel.client_id == ThirdPartyConsentLink.client_app_id)
            .join(Consent, Consent.id == ThirdPartyConsentLink.consent_id)
        )

    @property
    def select_plan_ids_in_wallet_query(self):
        return select(SchemeAccount.scheme_id).join(
            SchemeAccountUserAssociation, SchemeAccountUserAssociation.scheme_account_id == SchemeAccount.id
        )


@dataclass
class LoyaltyPlanHandler(BaseHandler, BaseLoyaltyPlanHandler):

    loyalty_plan_id: int
    loyalty_plan: Scheme = None
    loyalty_plan_credentials: dict = None
    consents: dict = None
    documents: dict = None
    manual_question: SchemeCredentialQuestion = None
    scan_question: SchemeCredentialQuestion = None

    def get_plan(self) -> dict:
        schemes_and_questions, scheme_info, consents, plan_ids_in_wallet = self._fetch_plan_information()
        sorted_plan_information = self._sort_info_by_plan(
            schemes_and_questions, scheme_info, consents, plan_ids_in_wallet
        )

        try:
            plan_info = list(sorted_plan_information.values())[0]
        except IndexError:
            raise ResourceNotFoundError(title="Could not find this Loyalty Plan")

        plan_info["credentials"] = self._sort_by_attr(plan_info["credentials"])
        plan_info["consents"] = self._sort_by_attr(plan_info["consents"], attr="consent.order")
        plan_info["documents"] = self._sort_by_attr(plan_info["documents"])

        journey_fields = self.get_journey_fields(
            plan=plan_info["plan"],
            creds=plan_info["credentials"],
            docs=plan_info["documents"],
            consents=plan_info["consents"],
        )

        resp = self._format_plan_data(
            plan_info["plan"],
            plan_info["images"],
            plan_info["tiers"],
            journey_fields,
            plan_info["contents"],
            plan_info["is_in_wallet"],
        )

        return resp

    def get_plan_details(self) -> dict:
        scheme_details = self._fetch_plan_information_details()
        sorted_plan_information = self._details_sort_info_by_plan(scheme_details)
        try:
            plan_info = list(sorted_plan_information.values())[0]
        except IndexError:
            raise ResourceNotFoundError(title="Could not find this Loyalty Plan")

        images = self._format_images(plan_info["images"])
        tiers = self._format_tiers(plan_info["tiers"])

        return {
            "company_name": plan_info["plan"].company,
            "plan_name": plan_info["plan"].name,
            "plan_label": plan_info["plan"].plan_name_card,
            "plan_url": plan_info["plan"].url,
            "plan_summary": plan_info["plan"].plan_summary,
            "plan_description": plan_info["plan"].plan_description,
            "redeem_instructions": plan_info["plan"].barcode_redeem_instructions,
            "plan_register_info": plan_info["plan"].plan_register_info,
            "join_incentive": plan_info["plan"].enrol_incentive,
            "category": plan_info["plan"].category.name,
            "tiers": tiers,
            "images": images,
        }

    def get_journey_fields(
        self,
        plan: Scheme = None,
        creds: list[SchemeCredentialQuestion] = None,
        docs: list[SchemeDocument] = None,
        consents: list[ThirdPartyConsentLink] = None,
    ) -> dict:

        # Check that all these variables were passed in as non None values, otherwise retrieve from db
        if not all([obj is not None for obj in [plan, creds, docs]]):
            plan, creds, docs = self._fetch_loyalty_plan_and_information()

        self.loyalty_plan = plan
        self.loyalty_plan_credentials = {}
        self._categorise_creds_and_docs(creds, docs)

        if consents is None:
            consents = self._fetch_consents()

        self._categorise_consents(consents)

        return self._format_journey_fields()

    def _fetch_plan_information(
        self,
    ) -> tuple[
        list[Row[Scheme, SchemeCredentialQuestion]],
        list[Row[SchemeDocument, SchemeImage, ThirdPartyConsentLink, SchemeDetail, SchemeContent]],
        list[Row[ThirdPartyConsentLink]],
        list[Row[int]],
    ]:

        schemes_query = self.select_plan_query.where(
            Channel.bundle_id == self.channel_id, Scheme.id == self.loyalty_plan_id
        )

        schemes_and_questions = self.db_session.execute(schemes_query).all()

        try:
            scheme_id = schemes_and_questions[0].Scheme.id
        except IndexError:
            raise ResourceNotFoundError(title="Could not find this Loyalty Plan")

        try:
            scheme_info_query = self.select_scheme_info_query.where(Scheme.id == scheme_id)
            scheme_info = self.db_session.execute(scheme_info_query).all()
            consent_query = self.select_consents_query.where(
                ThirdPartyConsentLink.scheme_id == scheme_id, Channel.bundle_id == self.channel_id
            )

            consents = self.db_session.execute(consent_query).all()
        except DatabaseError:
            api_logger.exception("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        in_wallet_query = self.select_plan_ids_in_wallet_query.where(
            SchemeAccountUserAssociation.user_id == self.user_id
        )
        plan_ids_in_wallet = self.db_session.execute(in_wallet_query).all()

        return schemes_and_questions, scheme_info, consents, plan_ids_in_wallet

    def _fetch_loyalty_plan_and_information(
        self,
    ) -> tuple[Scheme, list[SchemeCredentialQuestion], list[SchemeDocument]]:
        # Fetches Loyalty Plan (if exists), associated Credential Questions,
        # Plan Documents (if any) and Consents (if any)

        query = (
            select(Scheme, SchemeCredentialQuestion, SchemeDocument)
            .join(SchemeCredentialQuestion)
            .join(
                SchemeChannelAssociation,
                and_(
                    SchemeChannelAssociation.scheme_id == Scheme.id,
                    SchemeChannelAssociation.status == LoyaltyPlanChannelStatus.ACTIVE.value,
                ),
            )
            .join(Channel)
            .join(SchemeDocument, isouter=True)
            .where(Scheme.id == self.loyalty_plan_id, Channel.bundle_id == self.channel_id)
            .order_by(SchemeCredentialQuestion.order)
        )

        try:
            plan_information = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")

            raise falcon.HTTPInternalServerError

        if not plan_information:
            api_logger.error("No loyalty plan information/credentials returned")

            raise ResourceNotFoundError(title="Could not find this Loyalty Plan")

        schemes, creds, docs = list(zip(*plan_information))

        return schemes[0], creds, docs

    def _fetch_plan_information_details(self) -> list[Row[Scheme, SchemeImage, SchemeDetail]]:
        schemes_query = self.select_plan_details_query.where(
            Channel.bundle_id == self.channel_id, Scheme.id == self.loyalty_plan_id
        )

        try:
            scheme_details = self.db_session.execute(schemes_query).all()
        except DatabaseError:
            api_logger.exception("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        return scheme_details

    def _categorise_creds_and_docs(
        self, credentials: list[SchemeCredentialQuestion], documents: list[SchemeDocument]
    ) -> tuple[dict, dict]:
        # Removes duplicates but preserves order
        all_creds = list(dict.fromkeys(credentials))
        all_documents_dict = dict.fromkeys(documents)
        # noinspection PyTypeChecker
        all_documents_dict.pop(None, None)
        sorted_documents = self._sort_by_attr(list(all_documents_dict))

        categorised_creds = self._categorise_creds_by_class(all_creds)
        categorised_docs = self._categorise_documents_to_class(sorted_documents)

        return categorised_creds, categorised_docs

    def _categorise_consents(
        self, consents: Union[list[Row[Consent, ThirdPartyConsentLink]], list[ThirdPartyConsentLink]]
    ) -> None:
        # If the query to retrieve consent data is selecting attributes explicitly then the consents provided may not
        # be as the type hint suggests. So we can't just check the typing for a consent with isinstance() to
        # differentiate between if the "consent" object is a Consent or ThirdPartyConsentLink.

        self.consents = {}

        if consents and getattr(consents[0], "consent", False):
            # If consents = list[ThirdPartyConsentLink]
            for cred_class in CredentialClass:
                self.consents[cred_class] = []
                for consent in consents:
                    if getattr(consent, cred_class):
                        self.consents[cred_class].append(consent.consent)
        else:
            # If consents = list[Row[Consent, ThirdPartyConsentLink]]
            for cred_class in CredentialClass:
                self.consents[cred_class] = []
                for consent in consents:
                    if getattr(consent.ThirdPartyConsentLink, cred_class):
                        self.consents[cred_class].append(consent.Consent)

    def _categorise_creds_by_class(self, all_credentials: list) -> dict:
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

    def _categorise_documents_to_class(self, all_documents: list) -> dict:
        # Categorises docs by class
        self.documents = {}
        for doc_class in DocumentClass:
            self.documents[doc_class] = []
            for document in all_documents:
                if document and doc_class in document.display:
                    self.documents[doc_class].append(document)
        return self.documents

    def _fetch_consents(self) -> list[Row[Consent, ThirdPartyConsentLink]]:
        query = (
            select(Consent, ThirdPartyConsentLink)
            .join(ThirdPartyConsentLink)
            .join(ClientApplication)
            .join(Channel)
            .where(ThirdPartyConsentLink.scheme_id == self.loyalty_plan_id, Channel.bundle_id == self.channel_id)
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
            "is_scannable": cred.scan_question,
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


class LoyaltyPlansHandler(BaseHandler, BaseLoyaltyPlanHandler):
    def _fetch_all_plan_information(
        self,
    ) -> tuple[
        list[Row[Scheme, SchemeCredentialQuestion]],
        list[Row[SchemeDocument, SchemeImage, ThirdPartyConsentLink, SchemeDetail, SchemeContent]],
        list[Row[ThirdPartyConsentLink]],
        list[Row[int]],
    ]:

        try:
            schemes_query = self.select_plan_query.where(
                Channel.bundle_id == self.channel_id,
            )

            schemes_and_questions = self.db_session.execute(schemes_query).all()
            scheme_ids = list({row.Scheme.id for row in schemes_and_questions})
        except DatabaseError:
            api_logger.exception("Unable to fetch loyalty plan and question records from database")
            raise falcon.HTTPInternalServerError

        try:
            scheme_info_query = self.select_scheme_info_query.where(Scheme.id.in_(scheme_ids))
            scheme_info = self.db_session.execute(scheme_info_query).all()
            consent_query = self.select_consents_query.where(
                ThirdPartyConsentLink.scheme_id.in_(scheme_ids), Channel.bundle_id == self.channel_id
            )

            consents = self.db_session.execute(consent_query).all()

        except DatabaseError:
            api_logger.exception("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        try:
            in_wallet_query = self.select_plan_ids_in_wallet_query.where(
                SchemeAccountUserAssociation.user_id == self.user_id
            )
            plan_ids_in_wallet = self.db_session.execute(in_wallet_query).all()
        except DatabaseError:
            api_logger.exception(
                "Unable to fetch loyalty plan ids of loyalty accounts already in the user's wallet "
                f"(user_id={self.user_id})"
            )
            raise falcon.HTTPInternalServerError

        return schemes_and_questions, scheme_info, consents, plan_ids_in_wallet

    def _fetch_all_plan_information_overview(self) -> tuple[list[Row[Scheme, SchemeImage]], list[Row[int]]]:

        schemes_query = self.select_plan_and_images_query.where(Channel.bundle_id == self.channel_id)

        try:
            schemes_and_images = self.db_session.execute(schemes_query).all()

        except DatabaseError:
            api_logger.exception("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        try:
            in_wallet_query = self.select_plan_ids_in_wallet_query.where(
                SchemeAccountUserAssociation.user_id == self.user_id
            )
            plan_ids_in_wallet = self.db_session.execute(in_wallet_query).all()
        except DatabaseError:
            api_logger.exception(
                "Unable to fetch loyalty plan ids of loyalty accounts already in the user's wallet "
                f"(user_id={self.user_id})"
            )
            raise falcon.HTTPInternalServerError

        return schemes_and_images, plan_ids_in_wallet

    def _overview_sort_info_by_plan(
        self,
        plans_and_images: list[Row[Scheme, SchemeImage]],
        plan_ids_in_wallet: list[Row[int]],
    ) -> dict:
        plan_ids_in_wallet = {row[0] for row in plan_ids_in_wallet}

        sorted_plan_information = {}
        for row in plans_and_images:
            plan = row[0]

            if plan.id not in sorted_plan_information.keys():
                sorted_plan_information.update(
                    {plan.id: {"plan": plan, "is_in_wallet": plan.id in plan_ids_in_wallet, "images": []}}
                )

            if row[1]:
                sorted_plan_information[plan.id]["images"].append(row[1])

        return sorted_plan_information

    def get_all_plans(self) -> list:
        schemes_and_questions, scheme_info, consents, plan_ids_in_wallet = self._fetch_all_plan_information()
        sorted_plan_information = self._sort_info_by_plan(
            schemes_and_questions, scheme_info, consents, plan_ids_in_wallet
        )

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
                plan=plan_info["plan"],
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
                    plan_info["is_in_wallet"],
                )
            )

        return resp

    def get_all_plans_overview(self) -> list:
        schemes_and_images, plan_ids_in_wallet = self._fetch_all_plan_information_overview()
        sorted_plan_information = self._overview_sort_info_by_plan(schemes_and_images, plan_ids_in_wallet)

        resp = []

        for plan_info in sorted_plan_information.values():
            resp.append(
                self._format_plan_data_overview(
                    plan_info["plan"],
                    plan_info["images"],
                    plan_info["is_in_wallet"],
                )
            )

        return resp

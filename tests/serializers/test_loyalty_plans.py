import pytest
from pydantic import ValidationError

from app.api.serializers import (
    AlternativeCredentialSerializer,
    ConsentSerializer,
    CredentialSerializer,
    DocumentSerializer,
    ImageSerializer,
    JourneyFieldsByClassSerializer,
    LoyaltyPlanJourneyFieldsSerializer,
    LoyaltyPlanOverviewSerializer,
    LoyaltyPlanSerializer,
    PlanDetailsSerializer,
    PlanFeaturesJourneySerializer,
    PlanFeaturesSerializer,
)
from app.handlers.loyalty_plan import LoyaltyPlanJourney


@pytest.fixture
def consent_data():
    return {
        "order": 1,
        "consent_slug": "consent_slug_2",
        "is_acceptance_required": False,
        "description": "This is some really descriptive text right here",
    }


@pytest.fixture
def credential_data():
    return {
        "order": 3,
        "display_label": "Password",
        "validation": None,
        "description": None,
        "credential_slug": "password",
        "type": "text",
        "is_sensitive": False,
        "is_scannable": False,
    }


@pytest.fixture
def alternative_cred():
    return {
        "order": 2,
        "display_label": "Password_2",
        "validation": None,
        "description": None,
        "credential_slug": "password_2",
        "type": "text",
        "is_sensitive": False,
        "is_scannable": False,
    }


@pytest.fixture
def document_data():
    return {
        "name": "Test Document",
        "url": "https://testdocument.com",
        "description": "This is a test plan document",
        "is_acceptance_required": True,
    }


@pytest.fixture
def class_data(credential_data, document_data, consent_data):
    return {"credentials": [credential_data], "plan_documents": [document_data], "consents": [consent_data]}


@pytest.fixture
def journey_fields_data(class_data):
    return {
        "loyalty_plan_id": 15,
        "add_fields": class_data,
        "authorise_fields": {"credentials": []},
        "register_ghost_card_fields": {"credentials": []},
        "join_fields": {"credentials": []},
    }


@pytest.fixture
def journey_fields_data_no_join_fields(class_data):
    return {
        "loyalty_plan_id": 15,
        "add_fields": class_data,
        "authorise_fields": {"credentials": []},
        "register_ghost_card_fields": {"credentials": []},
    }


@pytest.fixture
def plan_features_journeys():
    return [
        {"type": 0, "description": LoyaltyPlanJourney.ADD},
        {"type": 1, "description": LoyaltyPlanJourney.AUTHORISE},
        {"type": 2, "description": LoyaltyPlanJourney.REGISTER},
        {"type": 3, "description": LoyaltyPlanJourney.JOIN},
    ]


def test_consents_serializer_as_expected(consent_data):

    serialized_consent = ConsentSerializer(**consent_data)

    for attribute in consent_data.keys():
        assert getattr(serialized_consent, attribute) == consent_data[attribute]


def test_consents_serializer_correct_casting(consent_data):
    consent_data["order"] = "18"
    consent_data["description"] = 301

    serialized_consent = ConsentSerializer(**consent_data)

    assert type(serialized_consent.order) == int
    assert type(serialized_consent.description) == str


def test_consents_serializer_error_extra_fields(consent_data):
    consent_data["extra_field"] = "1"

    with pytest.raises(ValidationError):
        ConsentSerializer(**consent_data)


def test_credential_serializer_as_expected(credential_data):

    serialized_credential = CredentialSerializer(**credential_data)

    for attribute in credential_data.keys():
        assert getattr(serialized_credential, attribute) == credential_data[attribute]


def test_credential_serializer_correct_casting(credential_data):
    credential_data["order"] = "18"
    credential_data["type"] = 7

    serialized_credential = CredentialSerializer(**credential_data)

    assert type(serialized_credential.order) == int
    assert type(serialized_credential.type) == str


def test_credential_serializer_error_extra_fields(credential_data):
    credential_data["extra_field"] = "1"

    with pytest.raises(ValidationError):
        CredentialSerializer(**credential_data)


def test_document_serializer_as_expected(document_data):

    serialized_document = DocumentSerializer(**document_data)

    for attribute in document_data.keys():
        assert getattr(serialized_document, attribute) == document_data[attribute]


def test_alt_credential_serializer_as_expected(alternative_cred):

    serialized_credential = AlternativeCredentialSerializer(**alternative_cred)

    for attribute in alternative_cred.keys():
        assert getattr(serialized_credential, attribute) == alternative_cred[attribute]


def test_document_serializer_error_extra_fields(document_data):
    document_data["extra_field"] = "1"

    with pytest.raises(ValidationError):
        DocumentSerializer(**document_data)


def test_class_serializer_as_expected(class_data):

    serialized_class = JourneyFieldsByClassSerializer(**class_data)

    assert len(serialized_class.credentials) == 1
    assert len(serialized_class.plan_documents) == 1
    assert len(serialized_class.consents) == 1


def test_journey_fields_serializer_as_expected(journey_fields_data):

    serialized_journey_fields = LoyaltyPlanJourneyFieldsSerializer(**journey_fields_data)

    assert serialized_journey_fields.loyalty_plan_id == journey_fields_data["loyalty_plan_id"]


def test_journey_fields_serializer_not_including_empty_fields(journey_fields_data_no_join_fields):

    serialized_journey_fields = LoyaltyPlanJourneyFieldsSerializer(**journey_fields_data_no_join_fields)

    response_data = serialized_journey_fields.dict()

    # Checks that join_fields key is found but the value is None
    assert response_data.get("join_fields", "NOTFOUND") is None


def test_plan_features_journey_serializer(plan_features_journeys):
    for journey in plan_features_journeys:
        serialized_journey = PlanFeaturesJourneySerializer(**journey).dict()
        assert journey["type"] == serialized_journey["type"]
        assert journey["description"].value == serialized_journey["description"]


def test_plan_features_serializer(plan_features_journeys):
    plan_features = {
        "has_points": True,
        "has_transactions": True,
        "plan_type": 0,
        "barcode_type": 0,
        "colour": "#FFFFFF",
        "text_colour": "#FFFFFF",
        "journeys": plan_features_journeys,
    }

    expected = {
        "has_points": True,
        "has_transactions": True,
        "plan_type": 0,
        "barcode_type": 0,
        "colour": "#FFFFFF",
        "text_colour": "#FFFFFF",
        "journeys": plan_features_journeys,
    }

    serialized_plan_features = PlanFeaturesSerializer(**plan_features).dict()

    assert expected == serialized_plan_features


def test_image_serializer():
    plan_features = {
        "id": 32,
        "type": 2,
        "url": "/some/url",
        "description": "some description here",
        "encoding": "png",
    }

    serialized_images = ImageSerializer(**plan_features).dict()

    assert plan_features == serialized_images


def test_plan_details_serializer():
    plan_details = {
        "company_name": "Some Company",
        "plan_name": "Plan name",
        "plan_label": "Label",
        "plan_url": "/some/url/here",
        "plan_summary": "what is this",
        "plan_description": "lorem ipsum etcetera",
        "redeem_instructions": "redeem some points",
        "plan_register_info": "yes",
        "join_incentive": "monies",
        "category": "household",
        "tiers": [{"name": "hello", "description": "world"}],
    }

    serialized_plan_features = PlanDetailsSerializer(**plan_details).dict()

    assert plan_details == serialized_plan_features


def test_loyalty_plan_serializer(loyalty_plan):
    expected = {
        "loyalty_plan_id": 1,
        "is_in_wallet": True,
        "plan_popularity": None,
        "plan_features": {
            "has_points": True,
            "has_transactions": True,
            "plan_type": 1,
            "barcode_type": None,
            "colour": "#22e892",
            "text_colour": "#22e893",
            "journeys": [
                {"type": 0, "description": LoyaltyPlanJourney.ADD},
                {"type": 1, "description": LoyaltyPlanJourney.AUTHORISE},
                {"type": 2, "description": LoyaltyPlanJourney.REGISTER},
                {"type": 3, "description": LoyaltyPlanJourney.JOIN},
            ],
        },
        "images": [
            {
                "id": 3,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
            {
                "id": 2,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
            {
                "id": 1,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
        ],
        "plan_details": {
            "company_name": "Flores, Reilly and Anderson",
            "plan_name": None,
            "plan_label": None,
            "plan_url": "https://www.testcompany244123.co.uk/testcompany",
            "plan_summary": None,
            "plan_description": None,
            "redeem_instructions": None,
            "plan_register_info": None,
            "join_incentive": None,
            "category": "Test Category",
            "tiers": [
                {
                    "name": "social",
                    "description": "Arm specific data someone his. Participant new really expert former tonight five",
                },
                {
                    "name": "market",
                    "description": "Arm specific data someone his. Participant new really expert former tonight five.",
                },
                {
                    "name": "team",
                    "description": "Arm specific data someone his. Participant new really expert former tonight five.",
                },
            ],
        },
        "journey_fields": {
            "join_fields": {
                "credentials": [
                    {
                        "order": 0,
                        "display_label": "Postcode",
                        "validation": None,
                        "description": None,
                        "credential_slug": "postcode",
                        "type": "text",
                        "is_sensitive": False,
                        "is_scannable": False,
                        "choice": [],
                        "alternative": None,
                    }
                ],
                "plan_documents": [
                    {
                        "order": 1,
                        "name": "Test Document",
                        "url": "https://testdocument.com",
                        "description": "This is a test plan document",
                        "is_acceptance_required": True,
                    },
                    {
                        "order": 2,
                        "name": "Test Document",
                        "url": "https://testdocument.com",
                        "description": "This is a test plan document",
                        "is_acceptance_required": True,
                    },
                    {
                        "order": 3,
                        "name": "Test Document",
                        "url": "https://testdocument.com",
                        "description": "This is a test plan document",
                        "is_acceptance_required": True,
                    },
                ],
                "consents": [
                    {
                        "order": 0,
                        "consent_slug": "consent_slug_4",
                        "is_acceptance_required": False,
                        "description": "This is some really descriptive text right here",
                    },
                    {
                        "order": 2,
                        "consent_slug": "consent_slug_3",
                        "is_acceptance_required": False,
                        "description": "This is some really descriptive text right here",
                    },
                    {
                        "order": 3,
                        "consent_slug": "consent_slug_1",
                        "is_acceptance_required": False,
                        "description": "This is some really descriptive text right here",
                    },
                ],
            },
            "register_ghost_card_fields": None,
            "add_fields": {
                "credentials": [
                    {
                        "order": 1,
                        "display_label": "Barcode",
                        "validation": None,
                        "description": None,
                        "credential_slug": "barcode",
                        "type": "text",
                        "is_sensitive": False,
                        "is_scannable": True,
                        "choice": [],
                        "alternative": {
                            "order": 1,
                            "display_label": "Card Number",
                            "validation": None,
                            "description": None,
                            "credential_slug": "card_number",
                            "type": "text",
                            "is_sensitive": False,
                            "is_scannable": False,
                            "choice": [],
                        },
                    }
                ],
                "plan_documents": [
                    {
                        "order": 1,
                        "name": "Test Document",
                        "url": "https://testdocument.com",
                        "description": "This is a test plan document",
                        "is_acceptance_required": True,
                    }
                ],
                "consents": [
                    {
                        "order": 3,
                        "consent_slug": "consent_slug_1",
                        "is_acceptance_required": False,
                        "description": "This is some really descriptive text right here",
                    }
                ],
            },
            "authorise_fields": {
                "credentials": [
                    {
                        "order": 3,
                        "display_label": "Memorable_date",
                        "validation": None,
                        "description": None,
                        "credential_slug": "memorable_date",
                        "type": "text",
                        "is_sensitive": False,
                        "is_scannable": False,
                        "choice": [],
                        "alternative": None,
                    },
                    {
                        "order": 6,
                        "display_label": "Email",
                        "validation": None,
                        "description": None,
                        "credential_slug": "email",
                        "type": "text",
                        "is_sensitive": False,
                        "is_scannable": False,
                        "choice": [],
                        "alternative": None,
                    },
                    {
                        "order": 9,
                        "display_label": "Password",
                        "validation": None,
                        "description": None,
                        "credential_slug": "password",
                        "type": "text",
                        "is_sensitive": False,
                        "is_scannable": False,
                        "choice": [],
                        "alternative": None,
                    },
                ],
                "plan_documents": [
                    {
                        "order": 1,
                        "name": "Test Document",
                        "url": "https://testdocument.com",
                        "description": "This is a test plan document",
                        "is_acceptance_required": True,
                    }
                ],
                "consents": [
                    {
                        "order": 1,
                        "consent_slug": "consent_slug_2",
                        "is_acceptance_required": False,
                        "description": "This is some really descriptive text right here",
                    }
                ],
            },
        },
        "content": [
            {
                "column": "federal",
                "value": "Although with meeting gas different bag hear.  Culture result suffer mention us.",
            },
            {
                "column": "event",
                "value": "Although with meeting gas different bag hear. Culture result suffer mention us.",
            },
            {
                "column": "laugh",
                "value": "Although with meeting gas different bag hear. Culture result suffer mention us.",
            },
        ],
    }
    serialized_plan = LoyaltyPlanSerializer(**loyalty_plan).dict()

    assert expected == serialized_plan


def test_loyalty_plan_overview_serializer(loyalty_plan_overview):
    expected = {
        "loyalty_plan_id": 1,
        "is_in_wallet": True,
        "plan_name": "Skynet Rewards",
        "company_name": "Skynet",
        "plan_popularity": None,
        "plan_type": 2,
        "colour": "#f80000",
        "text_colour": "#22e893",
        "category": "Robots",
        "images": [
            {
                "id": 3,
                "type": 3,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            }
        ],
    }
    serialized_plan = LoyaltyPlanOverviewSerializer(**loyalty_plan_overview).dict()

    assert expected == serialized_plan

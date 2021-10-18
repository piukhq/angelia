import pytest
from pydantic import ValidationError

from app.api.serializers import (
    AlternativeCredentialSerializer,
    ConsentSerializer,
    CredentialSerializer,
    DocumentSerializer,
    JourneyFieldsByClassSerializer,
    LoyaltyPlanJourneyFieldsSerializer,
)


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

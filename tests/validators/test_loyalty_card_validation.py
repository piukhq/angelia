import pytest
import voluptuous

from app.api.exceptions import ValidationError
from app.api.validators import (
    _validate_req_schema,
    consent_field_schema,
    loyalty_card_add_and_register_schema,
    loyalty_card_add_schema,
    loyalty_card_authorise_schema,
    loyalty_card_join_schema,
    loyalty_card_merchant_fields_schema,
    loyalty_card_register_schema,
    loyalty_card_trusted_add_account_schema,
    loyalty_card_trusted_add_schema,
    must_provide_single_add_or_auth_field,
)


class Context:
    validated_data = None


class TestReqObject:
    def __init__(self, media):
        self.media = media
        cxt = Context()
        cxt.validated_data = media
        self.context = cxt

    def get_media(self, default_when_empty=None):

        if self.media:
            return self.media
        else:
            return default_when_empty


VALID_LOYALTY_PLAN_ID = [0, 1]
INVALID_LOYALTY_PLAN_ID = ["", None, "1"]

VALID_ACCOUNT_ID = ["asacsq2323", "1"]
INVALID_ACCOUNT_ID = ["", None, 1]


def test_add_no_validation_issues():
    """Tests that there are no validation issues in normal circumstances"""
    req_data = {
        "loyalty_plan_id": 77,
        "account": {"add_fields": {"credentials": [{"credential_slug": "barcode", "value": "9511143200133540455525"}]}},
    }
    request = TestReqObject(req_data)
    _validate_req_schema(loyalty_card_add_schema, request)


def test_add_no_validation_issues_unknown_cred_slug():
    """Tests that there are no validation issues where cred fields are unknown"""
    req_data = {
        "loyalty_plan_id": 77,
        "account": {"add_fields": {"credentials": [{"credential_slug": "hat_height", "value": "152cm"}]}},
    }
    request = TestReqObject(req_data)
    _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_other_classes_included():
    """Tests that request is invalid where credential classes other than 'add_fields' are included"""
    req_data = {
        "loyalty_plan_id": 77,
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "barcode", "value": "9511143200133540455525"}],
                "auth_fields": {
                    "credentials": [{"credential_slug": "email", "value": "ilovetotest@testing.com"}],
                },
            }
        },
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_bad_field_name():
    """Tests that request is invalid where credential field names are incorrect"""

    req_data = {
        "loyalty_plan_id": 77,
        "account": {
            "add_fields": {
                "credentials": [{"we_call_this_credential": "barcode", "value": "9511143200133540455525"}],
            }
        },
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_multiple_add_fields():
    """Tests that request is invalid where more than one add_field is provided"""
    req_data = {
        "loyalty_plan_id": 77,
        "account": {
            "add_fields": {
                "credentials": [
                    {"credential_slug": "barcode", "value": "9511143200133540455525"},
                    {"credential_slug": "card_number", "value": "95111432001335404555254324"},
                ],
            },
        },
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_no_loyalty_plan():
    """Tests that request is invalid where loyalty plan field is not included"""

    req_data = {
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "barcode", "value": "9511143200133540455525"}],
            }
        }
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_schema, request)


@pytest.mark.parametrize("val", VALID_ACCOUNT_ID)
def test_loyalty_card_merchant_fields_schema_valid(val):
    schema = loyalty_card_merchant_fields_schema

    req_data = {"account_id": val}

    validated_data = schema(req_data)

    assert validated_data["merchant_identifier"] == val


@pytest.mark.parametrize("val", INVALID_ACCOUNT_ID)
def test_loyalty_card_merchant_fields_schema_invalid(val):
    schema = loyalty_card_merchant_fields_schema

    req_data = {"account_id": val}

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


def test_loyalty_card_merchant_fields_schema_invalid_account_id_key():
    schema = loyalty_card_merchant_fields_schema

    for val in [{}, {"notaccount_id": "assdw"}]:
        req_data = val

        with pytest.raises(voluptuous.MultipleInvalid):
            schema(req_data)


def test_must_provide_single_add_or_auth_field_valid(
    trusted_add_account_add_field_data, trusted_add_account_single_auth_field_data
):
    must_provide_single_add_or_auth_field(trusted_add_account_add_field_data)
    must_provide_single_add_or_auth_field(trusted_add_account_single_auth_field_data)


def test_must_provide_single_add_or_auth_field_invalid(trusted_add_req_data, merchant_fields_data):
    credentials_add_and_auth = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
        "authorise_fields": {"credentials": [{"credential_slug": "email", "value": "someemail@bink.com"}]},
        "merchant_fields": merchant_fields_data,
    }

    credentials_multi_add = {
        "add_fields": {
            "credentials": [
                {"credential_slug": "card_number", "value": "9511143200133540455525"},
                {"credential_slug": "barcode", "value": "9511143200133540455525"},
            ]
        },
        "merchant_fields": merchant_fields_data,
    }

    credentials_multi_auth = {
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "someemail@bink.com"},
                {"credential_slug": "password", "value": "somepass1"},
            ]
        },
        "merchant_fields": merchant_fields_data,
    }

    for credentials in (credentials_add_and_auth, credentials_multi_auth, credentials_multi_add):
        with pytest.raises(voluptuous.Invalid):
            must_provide_single_add_or_auth_field(credentials)


def test_loyalty_card_trusted_add_account_schema_valid_account_data(
    trusted_add_account_add_field_data, trusted_add_account_single_auth_field_data
):
    schema = loyalty_card_trusted_add_account_schema

    for req_data in [trusted_add_account_add_field_data, trusted_add_account_single_auth_field_data]:
        schema(req_data)


@pytest.mark.parametrize("required_field", ["merchant_fields"])
@pytest.mark.parametrize("val", ["", None, {}])
def test_loyalty_card_trusted_add_account_schema_required_fields_not_empty(
    val, required_field, trusted_add_account_add_field_data
):
    schema = loyalty_card_trusted_add_account_schema
    req_data = trusted_add_account_add_field_data

    req_data[required_field] = val

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


@pytest.mark.parametrize("val", VALID_LOYALTY_PLAN_ID)
def test_loyalty_card_trusted_add_schema_valid_loyalty_plan_id(val, trusted_add_req_data):
    schema = loyalty_card_trusted_add_schema
    req_data = trusted_add_req_data

    req_data["loyalty_plan_id"] = val

    schema(req_data)


@pytest.mark.parametrize("val", INVALID_LOYALTY_PLAN_ID)
def test_loyalty_card_trusted_add_schema_invalid_loyalty_plan_id(val, trusted_add_req_data):
    schema = loyalty_card_trusted_add_schema
    req_data = trusted_add_req_data

    req_data["loyalty_plan_id"] = val

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


@pytest.mark.parametrize("val", ["", None, {}])
def test_loyalty_card_trusted_add_schema_account_not_empty(val, trusted_add_req_data):
    schema = loyalty_card_trusted_add_schema
    req_data = trusted_add_req_data

    req_data["account"] = val

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


def test_add_and_register_invalid_missing_register_fields():
    """Tests that request is invalid where register fields are missing"""

    req_data = {
        "loyalty_plan_id": 77,
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "barcode", "value": "9511143200133540455525"}],
            }
        },
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_and_register_schema, request)


def test_add_and_register_valid():
    """Tests the add_and_register happy path"""

    req_data = {
        "loyalty_plan_id": 77,
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "barcode", "value": "9511143200133540455525"}],
            },
            "register_ghost_card_fields": {"credentials": [{"credential_slug": "postcode", "value": "GU225HT"}]},
        },
    }
    request = TestReqObject(req_data)

    _validate_req_schema(loyalty_card_add_and_register_schema, request)


def test_auth_valid():
    """Tests the authorise happy path"""

    req_data = {
        "account": {
            "authorise_fields": {
                "credentials": [{"credential_slug": "password", "value": "2398h9go2o"}],
            },
        },
    }
    request = TestReqObject(req_data)

    _validate_req_schema(loyalty_card_authorise_schema, request)


def test_register_valid():
    """Tests the register happy path"""

    req_data = {
        "account": {
            "register_ghost_card_fields": {
                "credentials": [{"credential_slug": "address", "value": "fake_address"}],
            },
        },
    }
    request = TestReqObject(req_data)

    _validate_req_schema(loyalty_card_register_schema, request)


def test_error_add_and_register_extra_fields():
    """Tests that request is invalid where extra fields are provided"""

    req_data = {
        "loyalty_plan_id": 77,
        "account": {
            "add_fields": {
                "credentials": [{"credential_slug": "barcode", "value": "9511143200133540455525"}],
            },
            "register_ghost_card_fields": {
                "credentials": [
                    {"credential_slug": "postcode", "value": "GU225HT"},
                ]
            },
            "extra_field": "ABCD",
        },
    }
    request = TestReqObject(req_data)

    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_and_register_schema, request)


def test_join_happy_path():
    """Tests happy path for join journey"""

    req_data = {
        "loyalty_plan_id": 77,
        "account": {
            "join_fields": {
                "credentials": [
                    {"credential_slug": "postcode", "value": "GU225HT"},
                ]
            },
        },
    }
    request = TestReqObject(req_data)

    _validate_req_schema(loyalty_card_join_schema, request)


def test_consent_validation():
    """Tests consent validation happy path"""

    req_data = {"consent_slug": "Consent_1", "value": "True"}
    request = TestReqObject(req_data)

    _validate_req_schema(consent_field_schema, request)


def test_consent_error_wrong_type():
    """Tests that request is invalid where consent is of the incorrect type"""

    req_data = {"consent_slug": "Consent_1", "value": True}
    request = TestReqObject(req_data)

    with pytest.raises(ValidationError):
        _validate_req_schema(consent_field_schema, request)

import pytest
import voluptuous

from angelia.api.exceptions import ValidationError
from angelia.api.validators import (
    _validate_req_schema,
    consent_field_schema,
    credential_field_schema,
    loyalty_card_add_and_auth_schema,
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
    validated_data: dict | None = None


class TestReqObject:
    def __init__(self, media: dict) -> None:
        self.media = media
        cxt = Context()
        cxt.validated_data = media
        self.context = cxt

    def get_media(self, default_when_empty: dict | None = None) -> dict | None:
        return self.media or default_when_empty


VALID_LOYALTY_PLAN_ID = [0, 1]
INVALID_LOYALTY_PLAN_ID = ["", None, "1"]

VALID_ACCOUNT_ID = ["asacsq2323", "1"]
INVALID_ACCOUNT_ID = ["", None, 1]


@pytest.mark.parametrize("required_field", ["credential_slug", "value"])
@pytest.mark.parametrize("val", ["", None, {}])
def test_credential_field_schema(
    val: str | dict | None, required_field: str, trusted_add_account_add_field_data: dict
) -> None:
    schema = credential_field_schema
    req_data = trusted_add_account_add_field_data["add_fields"]["credentials"][0]

    req_data[required_field] = val

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


def test_add_no_validation_issues() -> None:
    """Tests that there are no validation issues in normal circumstances"""
    req_data = {
        "loyalty_plan_id": 77,
        "account": {"add_fields": {"credentials": [{"credential_slug": "barcode", "value": "9511143200133540455525"}]}},
    }
    request = TestReqObject(req_data)
    _validate_req_schema(loyalty_card_add_schema, request)


def test_add_no_validation_issues_unknown_cred_slug() -> None:
    """Tests that there are no validation issues where cred fields are unknown"""
    req_data = {
        "loyalty_plan_id": 77,
        "account": {"add_fields": {"credentials": [{"credential_slug": "hat_height", "value": "152cm"}]}},
    }
    request = TestReqObject(req_data)
    _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_other_classes_included() -> None:
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


def test_add_invalid_bad_field_name() -> None:
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


def test_add_invalid_multiple_add_fields() -> None:
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


def test_add_invalid_no_loyalty_plan() -> None:
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
def test_loyalty_card_merchant_fields_schema_valid(val: str) -> None:
    schema = loyalty_card_merchant_fields_schema

    req_data = {"account_id": val}

    validated_data = schema(req_data)

    assert validated_data["merchant_identifier"] == val


@pytest.mark.parametrize("val", INVALID_ACCOUNT_ID)
def test_loyalty_card_merchant_fields_schema_invalid(val: str | int | None) -> None:
    schema = loyalty_card_merchant_fields_schema

    req_data = {"account_id": val}

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


def test_loyalty_card_merchant_fields_schema_invalid_account_id_key() -> None:
    schema = loyalty_card_merchant_fields_schema

    for val in ({}, {"notaccount_id": "assdw"}):
        req_data = val

        with pytest.raises(voluptuous.MultipleInvalid):
            schema(req_data)


def test_must_provide_single_add_or_auth_field_valid(
    trusted_add_account_add_field_data: dict, trusted_add_account_single_auth_field_data: dict
) -> None:
    must_provide_single_add_or_auth_field(trusted_add_account_add_field_data)
    must_provide_single_add_or_auth_field(trusted_add_account_single_auth_field_data)


def test_must_provide_single_add_or_auth_field_invalid(trusted_add_req_data: dict, merchant_fields_data: dict) -> None:
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

    credentials_fields_with_no_creds = {
        "add_fields": {"credentials": []},
        "authorise_fields": {"credentials": []},
        "merchant_fields": merchant_fields_data,
    }

    credentials_add_fields_with_no_creds = {
        "add_fields": {"credentials": []},
        "merchant_fields": merchant_fields_data,
    }

    credentials_auth_fields_with_no_creds = {
        "authorise_fields": {"credentials": []},
        "merchant_fields": merchant_fields_data,
    }

    credentials_no_cred_fields = {
        "merchant_fields": merchant_fields_data,
    }

    for credentials in (
        credentials_add_and_auth,
        credentials_multi_auth,
        credentials_multi_add,
        credentials_fields_with_no_creds,
        credentials_add_fields_with_no_creds,
        credentials_auth_fields_with_no_creds,
        credentials_no_cred_fields,
    ):
        with pytest.raises(voluptuous.Invalid):
            must_provide_single_add_or_auth_field(credentials)


def test_loyalty_card_trusted_add_account_schema_valid_account_data(
    trusted_add_account_add_field_data: dict, trusted_add_account_single_auth_field_data: dict
) -> None:
    schema = loyalty_card_trusted_add_account_schema

    for req_data in (trusted_add_account_add_field_data, trusted_add_account_single_auth_field_data):
        schema(req_data)


@pytest.mark.parametrize("required_field", ["merchant_fields"])
@pytest.mark.parametrize("val", ["", None, {}])
def test_loyalty_card_trusted_add_account_schema_required_fields_not_empty(
    val: str | dict | None, required_field: str, trusted_add_account_add_field_data: dict
) -> None:
    schema = loyalty_card_trusted_add_account_schema
    req_data = trusted_add_account_add_field_data

    req_data[required_field] = val

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


@pytest.mark.parametrize("val", VALID_LOYALTY_PLAN_ID)
def test_loyalty_card_trusted_add_schema_valid_loyalty_plan_id(
    val: int | None | str, trusted_add_req_data: dict
) -> None:
    schema = loyalty_card_trusted_add_schema
    req_data = trusted_add_req_data

    req_data["loyalty_plan_id"] = val

    schema(req_data)


@pytest.mark.parametrize("val", INVALID_LOYALTY_PLAN_ID)
def test_loyalty_card_trusted_add_schema_invalid_loyalty_plan_id(
    val: int | None | str, trusted_add_req_data: dict
) -> None:
    schema = loyalty_card_trusted_add_schema
    req_data = trusted_add_req_data

    req_data["loyalty_plan_id"] = val

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


@pytest.mark.parametrize("val", ("", None, {}))
def test_loyalty_card_trusted_add_schema_account_not_empty(val: str | dict | None, trusted_add_req_data: dict) -> None:
    schema = loyalty_card_trusted_add_schema
    req_data = trusted_add_req_data

    req_data["account"] = val

    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


def test_loyalty_card_add_and_auth_schema_valid_account_data(add_and_auth_req_data: dict, add_req_data: dict) -> None:
    schema = loyalty_card_add_and_auth_schema

    # add_and_auth schema allows a single add field with no auth for add-only links e.g The Works
    for req_data in (add_and_auth_req_data, add_req_data):
        schema(req_data)


def test_add_and_register_invalid_missing_register_fields() -> None:
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


def test_add_and_register_valid() -> None:
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


def test_auth_valid() -> None:
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


def test_register_valid() -> None:
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


def test_error_add_and_register_extra_fields() -> None:
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


def test_join_happy_path() -> None:
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


def test_consent_validation() -> None:
    """Tests consent validation happy path"""

    req_data = {"consent_slug": "Consent_1", "value": "True"}
    request = TestReqObject(req_data)

    _validate_req_schema(consent_field_schema, request)


def test_consent_error_wrong_type() -> None:
    """Tests that request is invalid where consent is of the incorrect type"""

    req_data = {"consent_slug": "Consent_1", "value": True}
    request = TestReqObject(req_data)

    with pytest.raises(ValidationError):
        _validate_req_schema(consent_field_schema, request)

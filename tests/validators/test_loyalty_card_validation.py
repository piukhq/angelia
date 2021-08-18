import pytest

from app.api.exceptions import ValidationError
from app.api.validators import _validate_req_schema, loyalty_card_add_schema


class TestReqObject:
    def __init__(self, media):
        self.media = media


def test_add_no_validation_issues():
    """Tests that there are no validation issues in normal circumstances"""
    req_data = {
        "loyalty_plan": 77,
        "account": {"add_fields": [{"credential_slug": "barcode", "value": "9511143200133540455525"}]},
    }
    request = TestReqObject(req_data)
    _validate_req_schema(loyalty_card_add_schema, request)


def test_add_no_validation_issues_unknown_cred_slug():
    """Tests that there are no validation issues where cred fields are unknown"""
    req_data = {"loyalty_plan": 77, "account": {"add_fields": [{"credential_slug": "hat_height", "value": "152cm"}]}}
    request = TestReqObject(req_data)
    _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_other_classes_included():
    """Tests that request is invalid where credential classes other than 'add_fields' are included"""
    req_data = {
        "loyalty_plan": 77,
        "account": {
            "add_fields": [{"credential_slug": "barcode", "value": "9511143200133540455525"}],
            "auth_fields": [{"credential_slug": "email", "value": "ilovetotest@testing.com"}],
        },
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_bad_field_name():
    """Tests that request is invalid where credential field names are incorrect"""

    req_data = {
        "loyalty_plan": 77,
        "account": {
            "add_fields": [{"we_call_this_credential": "barcode", "value": "9511143200133540455525"}],
        },
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_multiple_add_fields():
    """Tests that request is invalid where more than one add_field is provided"""
    req_data = {
        "loyalty_plan": 77,
        "account": {
            "add_fields": [
                {"credential_slug": "barcode", "value": "9511143200133540455525"},
                {"credential_slug": "card_number", "value": "95111432001335404555254324"},
            ],
        },
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_schema, request)


def test_add_invalid_no_loyalty_plan():
    """Tests that request is invalid where loyalty plan field is not included"""

    req_data = {
        "account": {
            "add_fields": [{"credential_slug": "barcode", "value": "9511143200133540455525"}],
        }
    }
    request = TestReqObject(req_data)
    with pytest.raises(ValidationError):
        _validate_req_schema(loyalty_card_add_schema, request)

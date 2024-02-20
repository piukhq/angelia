import pytest
from voluptuous import MultipleInvalid

from angelia.api.validators import email_update_schema

VALID_EMAILS = ["test_email@email.com", "TesT_emAil@email.domain", "3375Ts3E@email.s3"]
INVALID_EMAILS = ["bonk", "bad@email", "@email.com", "bad.com", "bad@.com", "bad@email.3"]


@pytest.mark.parametrize("valid_email", VALID_EMAILS)
def test_email_update_validator(valid_email: str) -> None:
    """Tests happy path for email_update journey"""

    req_data = {"email": valid_email}

    email_update_schema(req_data)


@pytest.mark.parametrize("invalid_email", INVALID_EMAILS)
def test_error_email_validation(invalid_email: str) -> None:
    req_data = {"email": invalid_email}

    with pytest.raises(MultipleInvalid):
        email_update_schema(req_data)

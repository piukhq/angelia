import pytest

from app.api.exceptions import ValidationError
from app.api.validators import _validate_req_schema, email_update_schema


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


def test_email_update_validator():
    """Tests happy path for email_update journey"""

    req_data = {"email": "test_email@email.com"}
    request = TestReqObject(req_data)

    _validate_req_schema(email_update_schema, request)


def test_error_email_validation():

    req_data = {"email": "test_email@com"}
    request = TestReqObject(req_data)

    with pytest.raises(ValidationError):
        _validate_req_schema(email_update_schema, request)

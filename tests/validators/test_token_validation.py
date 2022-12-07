import pytest
import voluptuous

from app.api.validators import token_schema


@pytest.fixture
def token_req_data():
    return {"grant_type": "b2b", "scope": ["user"]}


REQUIRED_FIELDS = ["grant_type", "scope"]


def test_token_schema_valid(token_req_data):
    schema = token_schema
    validated_data = schema(token_req_data)

    assert 2 == len(validated_data)
    assert "b2b" == validated_data["grant_type"]
    assert ["user"] == validated_data["scope"]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_token_schema_required_fields_not_empty(token_req_data, field):
    schema = token_schema

    token_req_data[field] = ""
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(token_req_data)

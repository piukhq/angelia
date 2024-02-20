import pytest
import voluptuous

from angelia.api.validators import token_schema


@pytest.fixture
def token_req_data() -> dict:
    return {"grant_type": "b2b", "scope": ["user"]}


REQUIRED_FIELDS = ["grant_type", "scope"]


def test_token_schema_valid(token_req_data: dict) -> None:
    schema = token_schema
    validated_data = schema(token_req_data)

    assert len(validated_data) == 2
    assert validated_data["grant_type"] == "b2b"
    assert ["user"] == validated_data["scope"]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_token_schema_required_fields_not_empty(token_req_data: dict, field: str) -> None:
    schema = token_schema

    token_req_data[field] = ""
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(token_req_data)

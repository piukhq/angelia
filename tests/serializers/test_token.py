import pytest

from app.api.serializers import TokenSerializer


@pytest.fixture
def post_token_data():
    return {
        "access_token": "eysdfgsdfgds",
        "token_type": "bearer",
        "expires_in": 600,
        "refresh_token": "eyfgfnfnbrgf",
        "scope": ["user"],
    }


def test_token_serializer(post_token_data):
    serialized_token = TokenSerializer(**post_token_data).dict()

    assert post_token_data == serialized_token

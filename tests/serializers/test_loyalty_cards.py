import pytest

from app.api.serializers import LoyaltyCardSerializer


@pytest.fixture
def loyalty_card_data() -> dict:
    return {
        "id": 1,
    }


def test_loyalty_card_serializer(loyalty_card_data: dict) -> None:
    serialized_data = LoyaltyCardSerializer(**loyalty_card_data)

    assert serialized_data.id == loyalty_card_data["id"]


def test_loyalty_card_serializer_casting(loyalty_card_data: dict) -> None:
    serialized_data = LoyaltyCardSerializer(**loyalty_card_data)

    loyalty_card_data["id"] = "1"

    assert isinstance(serialized_data.id, int)

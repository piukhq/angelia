from app.api.validators import (
    _validate_req_schema,
    loyalty_card_join_schema,
)


class TestReqObject:
    def __init__(self, media):
        self.media = media

    def get_media(self, default_when_empty=None):

        if self.media:
            return self.media
        else:
            return default_when_empty


def test_join_happy_path():
    """Tests happy path for join journey"""

    req_data = {"email": "test_email@email.com"}
    request = TestReqObject(req_data)

    _validate_req_schema(loyalty_card_join_schema, request)
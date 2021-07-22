import falcon
import jwt
from unittest.mock import Mock, patch
from app.api.auth import BaseJwtAuth, AccessToken, get_authenticated_user, get_authenticated_channel


class MockContext:
    auth_obj = AccessToken()
    auth_instance = auth_obj


def setup_mock_request(auth_header):
    mock_request = Mock(spec=falcon.Request)
    mock_request.context = MockContext
    mock_request.auth = auth_header
    return mock_request


def test_auth():
    with patch.dict("app.api.auth.vault_access_secret", {"access-secret-1": "my_secret_1"}):
        mock_request = setup_mock_request("bearer eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCIsImtpZCI6ImFjY2Vzcy1zZWNyZXQtMSJ9.eyJjaGFubmVsIjoiY29tX2Jpbmsud2FsbGV0Iiwic3ViIjozOTYyNCwiZXhwIjoxNjI2ODk0MjY1LCJpYXQiOjE2MjY4OTMzNjV9.1V1nfuVa0JhT9E1dUxvRENpanl6ahiFMY0dtijHfIhoxhlL9pJhy8HqLb1x0CbMqiZuZEgt7XXGsxERUW8r5wg")
        auth_obj = mock_request.context.auth_instance
        auth_obj.validate(mock_request)
        assert get_authenticated_user(mock_request) == 39624
        assert get_authenticated_channel(mock_request) == "com_bink.wallet"

from unittest.mock import patch

from falcon import testing
from app.api import app
from tests.authentication.test_access_token import create_access_token


def get_client():
    with patch("app.api.app.load_secrets") as mock_load:
        mock_load.return_value = None
        return testing.TestClient(app.create_app())


def get_authenticated_request(method, path, json=None, user_id=1, channel="com.test.channel"):
    test_secret_key = "test_key-1"
    auth_dict = {test_secret_key: "test_mock_secret_1"}

    with patch("app.api.auth.get_access_token_secret") as mock_get_secret:
        mock_get_secret.return_value = auth_dict[test_secret_key]
        auth_token = create_access_token(test_secret_key, auth_dict, user_id, channel)

        resp = get_client().simulate_request(
            path=path, json=json, headers={"Authorization": auth_token}, method=method)
        return resp

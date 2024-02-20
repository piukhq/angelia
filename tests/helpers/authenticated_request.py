from unittest.mock import patch

from falcon import Response, testing

from angelia.api import app
from tests.authentication.test_access_token import create_access_token


def get_client() -> testing.TestClient:
    with patch("angelia.api.app.load_secrets") as mock_load:
        mock_load.return_value = None
        return testing.TestClient(app.create_app())


def get_authenticated_request(
    method: str,
    path: str,
    json: str | dict | None = None,
    body: str | bytes | None = None,
    user_id: int = 1,
    channel: str = "com.test.channel",
    is_tester: bool = False,
    is_trusted_channel: bool = False,
) -> Response:
    test_secret_key = "test_key-1"
    auth_dict = {test_secret_key: "test_mock_secret_1"}

    with patch("angelia.api.auth.get_access_token_secret") as mock_get_secret:
        mock_get_secret.return_value = auth_dict[test_secret_key]
        auth_token = create_access_token(test_secret_key, auth_dict, user_id, channel, is_tester, is_trusted_channel)

        resp = get_client().simulate_request(
            path=path, json=json, body=body, headers={"Authorization": auth_token}, method=method
        )
        return resp

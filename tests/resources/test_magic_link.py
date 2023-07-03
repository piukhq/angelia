from falcon import HTTP_202
from pytest_mock import MockerFixture

from tests.helpers.authenticated_request import get_authenticated_request


def test_access_tokens_on_post(mocker: MockerFixture) -> None:
    sample_token = "sample value"

    mock_response = {"access_token": "test value"}
    mock_handler = mocker.MagicMock()
    mocker.patch("app.resources.magic_link.MagicLinkHandler", return_value=mock_handler)
    mock_handler.get_or_create_user.return_value = mock_response

    resp = get_authenticated_request(method="POST", path="/v2/magic_link/access_token", json={"token": sample_token})

    assert resp.status == HTTP_202
    assert resp.json == mock_response

    mock_handler.get_or_create_user.assert_called_once_with(sample_token)

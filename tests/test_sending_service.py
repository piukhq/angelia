from collections.abc import Callable

import pytest
from loguru import logger
from pytest_mock import MockFixture

from app.messaging.sender import SendingService
from settings import PUBLISH_MAX_RETRIES, PUBLISH_RETRY_BACKOFF_FACTOR


@pytest.mark.parametrize(
    ("pub_side_effect", "expected_retry_n"),
    [
        pytest.param(
            lambda *_: None,
            0,
            id="Test success with no retries",
        ),
        pytest.param(
            ValueError("sample connection error"),
            -1,
            id="Test max retries exceeded",
        ),
    ]
    + [
        pytest.param(
            [ValueError("sample connection error")] * i + [lambda *_: None],
            i,
            id=f"Test success after {i} retry.",
        )
        for i in range(1, PUBLISH_MAX_RETRIES + 1)
    ],
)
def test__pub_retry(pub_side_effect: Callable | list[Callable], expected_retry_n: int, mocker: MockFixture) -> None:
    mock_logger = mocker.MagicMock(spec=logger)
    mock_opt_logger = mocker.MagicMock(spec=logger)
    mock_logger.opt.return_value = mock_opt_logger

    def mock_init(self: SendingService, *_: str) -> None:
        self._conn = None
        self.producer = {}
        self.queue = {}
        self.exchange = {}
        self.logger = mock_logger

    mocker.patch.object(SendingService, "__init__", mock_init)
    mock_connect = mocker.patch.object(SendingService, "connect")
    mock_close = mocker.patch.object(SendingService, "close")
    mock_pub = mocker.patch.object(SendingService, "_pub")
    mock_sleep = mocker.patch("app.messaging.message_broker.sleep")

    mock_pub.side_effect = pub_side_effect

    service = SendingService("")
    raised_exc: Exception | None = None

    try:
        service.send({}, {}, "test-queue")
    except Exception as e:
        raised_exc = e

    match expected_retry_n:
        case 0:
            mock_connect.assert_not_called()
            mock_close.assert_not_called()
            mock_logger.warning.assert_not_called()
            mock_logger.opt.assert_not_called()
            mock_logger.opt.error.assert_not_called()
            mock_sleep.assert_not_called()
            assert not raised_exc

        case -1:
            assert mock_connect.call_count == PUBLISH_MAX_RETRIES
            assert mock_close.call_count == PUBLISH_MAX_RETRIES
            assert mock_logger.warning.call_count == PUBLISH_MAX_RETRIES
            mock_logger.opt.assert_called_once_with(exception=pub_side_effect)
            mock_opt_logger.error.assert_called_once_with("Failed to send message, max retries exceeded.")
            assert {i * PUBLISH_RETRY_BACKOFF_FACTOR for i in range(PUBLISH_MAX_RETRIES)} == (
                {call.args[0] for call in mock_sleep.call_args_list}
            )
            assert raised_exc == pub_side_effect

            # -------------------------------------- Warning --------------------------------------- #
            assert sum(i * PUBLISH_RETRY_BACKOFF_FACTOR for i in range(PUBLISH_MAX_RETRIES)) <= 1.5, (
                "Warning: this combination of PUBLISH_RETRY_BACKOFF_FACTOR and PUBLISH_MAX_RETRIES "
                "can result in a wait time of over 1.5 seconds for a synchronous call. "
                "If this is intentional, delete this assertion."
            )
            # -------------------------------------------------------------------------------------- #

        case _:
            assert mock_connect.call_count == expected_retry_n
            assert mock_close.call_count == expected_retry_n
            assert mock_logger.warning.call_count == expected_retry_n - 1
            mock_logger.opt.assert_not_called()
            mock_opt_logger.error.assert_not_called()
            assert {i * PUBLISH_RETRY_BACKOFF_FACTOR for i in range(expected_retry_n)} == (
                {call.args[0] for call in mock_sleep.call_args_list}
            )
            assert not raised_exc

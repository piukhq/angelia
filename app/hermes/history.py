import kombu
import kombu.exceptions
from amqp import AMQPError

from app.hermes.utils import HistoryData
from app.messaging.sender import send_message_to_hermes
from app.report import history_logger


class HistoryEvent:
    """
    Simple handler to manage state for a single History message.
    """

    message_sent: bool = False

    class DataError(Exception):
        """Raised when initialising the class without a valid object of type HistoryData"""

    def __init__(self, data: HistoryData) -> None:
        if not data or not isinstance(data, HistoryData):
            raise self.DataError("Cannot instantiate a HistorySession without valid HistoryData")

        self.data = data

    def __repr__(self) -> str:
        return (
            f"HistorySession(user_id={self.data.user_id}, table={self.data.table}, "
            f"event_type={self.data.event_type.value})"
        )

    def try_dispatch(self, retry_count: int = 3) -> bool:
        """
        Attempts to send message to Hermes and returns a True if successful, otherwise False.

        If the send fails due to a queue related error, it will attempt to retry for a total of 3
        send attempts by default before returning.
        """
        if not self.message_sent:
            payload = self.data.to_dict()
            event_name = payload.pop("event_name")
            while retry_count:
                try:
                    send_message_to_hermes(event_name, payload)
                    self.message_sent = True
                    break
                except (kombu.exceptions.KombuError, AMQPError) as e:
                    if retry_count > 0:
                        history_logger.warning(f"Error occurred sending History message - {self}; Retrying - {e!r}")
                        retry_count -= 1
                    else:
                        history_logger.warning(
                            f"Error occurred sending History message - {self}; Retry attempts failed."
                            f"Event details - {payload}"
                        )

        return self.message_sent


class HistoryStorage:
    def __init__(self) -> None:
        self._events: list[HistoryEvent] = []

    def register_event(self, event: HistoryEvent) -> None:
        self._events.append(event)

    def process_events(self) -> None:
        while self._events:
            # pop from the front so the events are sent in order of transaction, though this isn't
            # 100% necessary since they have timestamps and will requeue after failures anyway
            history_event = self._events.pop(0)
            message_sent = history_event.try_dispatch()

            if not message_sent:
                # Message was not sent so requeue.
                self._events.append(history_event)
                history_logger.debug(f"History session failed to send. Re-queuing - {history_event}")


history_storage = HistoryStorage()

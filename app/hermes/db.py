import time
from typing import TYPE_CHECKING, Any, Self

import kombu
import kombu.exceptions
from amqp import AMQPError
from sqlalchemy import MetaData, create_engine, event, orm
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

import settings
from app.hermes.utils import EventType, HistoryData
from app.lib.singletons import Singleton
from app.messaging.sender import mapper_history, send_message_to_hermes
from app.report import history_logger, sql_logger
from settings import POSTGRES_CONNECT_ARGS, POSTGRES_DSN, TESTING

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.engine import cursor as sqla_cursor
    from sqlalchemy.orm import DeclarativeMeta, Session

    from app.hermes.models import ModelBase

    TargetType = type[ModelBase]


class DB(metaclass=Singleton):
    """This is a singleton class to manage sessions.

    To use the singleton import the DB class then:

    DB().open_write() or DB().open_read()  at start of request ie in middleware
    DB().session   to get the session in database layer
    DB().session.close() to close the session at the end of request in middleware

    For non api code use in with statement:

    with DB().open_write() as session:
    with DB().open_read() as session:


    """

    def __init__(self) -> None:
        """Note as a singleton will only run on first instantiation"""
        # test_engine is used only for tests to copy the hermes schema to the hermes_test db
        if TESTING:
            self.test_engine = create_engine(POSTGRES_DSN, connect_args=POSTGRES_CONNECT_ARGS)
            self.engine = create_engine(f"{POSTGRES_DSN}_test", connect_args=POSTGRES_CONNECT_ARGS)
            self.metadata = MetaData(bind=self.test_engine)
        else:
            self.engine = create_engine(POSTGRES_DSN, connect_args=POSTGRES_CONNECT_ARGS)
            self.metadata = MetaData(bind=self.engine)

        self.Base: "DeclarativeMeta" = declarative_base()

        self.Session = scoped_session(sessionmaker(bind=self.engine, future=True))
        self.session: "Session | None" = None

        self._init_session_event_listeners()

        self.history_sessions: list[HistorySession] = []

        if settings.QUERY_LOGGING:
            # Adds event hooks to before and after query executions to log queries and execution times.
            @event.listens_for(self.engine, "before_cursor_execute")
            def before_cursor_execute(  # noqa: PLR0913
                conn: "Connection",
                cursor: "sqla_cursor",
                statement: str,
                parameters: list,
                context: dict,
                executemany: bool,
            ) -> None:
                conn.info.setdefault("query_start_time", []).append(time.time())
                sql_logger.debug(f"Start Query: {statement}")

            @event.listens_for(self.engine, "after_cursor_execute")
            def after_cursor_execute(  # noqa: PLR0913
                conn: "Connection",
                cursor: "sqla_cursor",
                statement: str,
                parameters: list,
                context: dict,
                executemany: bool,
            ) -> None:
                total = time.time() - conn.info["query_start_time"].pop(-1)
                sql_logger.debug("Query Complete!")
                sql_logger.debug(f"Total Time: {total}")

    def __enter__(self) -> "Session | None":
        """Return session to the variable referenced in the "with as" statement"""
        return self.session

    def __exit__(self, exc_type: type[Exception], exc_val: Exception, exc_tb: Any) -> None:
        self.close()

    def open(self) -> Self:  # noqa: A003
        """Returns self to allow with clause to work and to allow chaining eg db().open_read().session"""
        self.session = self.Session()
        return self

    def close(self) -> None:
        if self.session:
            self.session.close()

    def _init_session_event_listeners(self) -> None:
        event.listen(self.Session, "after_commit", self.after_commit_listener)

    def init_mapper_event_listeners(self, watched_classes: list) -> None:
        """
        Initialises event listeners for after update, insert, and deletes of given list of mappers
        These listeners execute before the transaction is committed to the database.
        """
        for w_class in watched_classes:
            event.listen(w_class, "after_update", self.history_after_update_listener)
            event.listen(w_class, "after_insert", self.history_after_insert_listener)
            event.listen(w_class, "after_delete", self.history_after_delete_listener)

    def history_after_insert_listener(
        self, mapped: orm.Mapper, connection: "Connection", target: "TargetType"  # noqa: ARG002
    ) -> None:
        if event_data := mapper_history(target, EventType.CREATE, mapped):
            self.history_sessions.append(HistorySession(data=event_data))

    def history_after_delete_listener(
        self, mapped: orm.Mapper, connection: "Connection", target: "TargetType"  # noqa: ARG002
    ) -> None:
        if event_data := mapper_history(target, EventType.DELETE, mapped):
            self.history_sessions.append(HistorySession(data=event_data))

    def history_after_update_listener(
        self, mapped: orm.Mapper, connection: "Connection", target: "TargetType"  # noqa: ARG002
    ) -> None:
        if event_data := mapper_history(target, EventType.UPDATE, mapped):
            self.history_sessions.append(HistorySession(data=event_data))

    def after_commit_listener(self, session: "Session") -> None:  # noqa: ARG002
        while self.history_sessions:
            # pop from the front so the events are sent in order of transaction, though this isn't
            # 100% necessary since they have timestamps and will requeue after failures anyway
            history_session = self.history_sessions.pop(0)
            message_sent = history_session.try_dispatch()

            if not message_sent:
                # Message was not sent so requeue.
                self.history_sessions.append(history_session)
                history_logger.debug(f"History session failed to send. Re-queuing - {history_session}")


class HistorySession:
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

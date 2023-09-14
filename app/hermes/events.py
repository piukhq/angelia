import time
from typing import TYPE_CHECKING

from sqlalchemy import event

from app.hermes.history import HistoryEvent, history_storage
from app.hermes.utils import EventType
from app.messaging.sender import mapper_history
from app.report import sql_logger
from settings import QUERY_LOGGING

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.engine import cursor as sqla_cursor
    from sqlalchemy.orm import Mapper, Session

    from app.hermes.db.models import ModelBase

    TargetType = type[ModelBase]


def _history_after_insert_listener(mapped: "Mapper", connection: "Connection", target: "TargetType") -> None:
    if event_data := mapper_history(target, EventType.CREATE, mapped):
        history_storage.register_event(HistoryEvent(data=event_data))


def _history_after_delete_listener(mapped: "Mapper", connection: "Connection", target: "TargetType") -> None:
    if event_data := mapper_history(target, EventType.DELETE, mapped):
        history_storage.register_event(HistoryEvent(data=event_data))


def _history_after_update_listener(mapped: "Mapper", connection: "Connection", target: "TargetType") -> None:
    if event_data := mapper_history(target, EventType.UPDATE, mapped):
        history_storage.register_event(HistoryEvent(data=event_data))


def _after_commit_listener(session: "Session") -> None:
    history_storage.process_events()


def init_events(db_session: "Session", watched_classes: "list[TargetType]") -> None:
    event.listen(db_session, "after_commit", _after_commit_listener)

    for w_class in watched_classes:
        event.listen(w_class, "after_update", _history_after_update_listener)
        event.listen(w_class, "after_insert", _history_after_insert_listener)
        event.listen(w_class, "after_delete", _history_after_delete_listener)

    if QUERY_LOGGING:
        # Adds event hooks to before and after query executions to log queries and execution times.
        @event.listens_for(db_session.engine, "before_cursor_execute")
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

        @event.listens_for(db_session.engine, "after_cursor_execute")
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

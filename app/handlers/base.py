from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass
class BaseTokenHandler:
    db_session: Session


@dataclass
class BaseHandler:
    db_session: Session
    user_id: int
    channel_id: str
    path: str

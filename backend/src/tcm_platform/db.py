from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from tcm_platform.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True,
                       connect_args={"connect_timeout": 3})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    with SessionLocal() as session, session.begin():
        yield session


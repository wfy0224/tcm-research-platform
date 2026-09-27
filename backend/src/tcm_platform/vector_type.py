"""Minimal SQLAlchemy type for PostgreSQL pgvector without a runtime adapter dependency."""

import math

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_kw):
        return "vector"

    def bind_processor(self, _dialect):
        def encode(value):
            if isinstance(value, str):
                return value
            numbers = [float(number) for number in value]
            if not numbers or any(not math.isfinite(number) for number in numbers):
                raise ValueError("embedding vector must contain finite values")
            return "[" + ",".join(str(number) for number in numbers) + "]"

        return encode


ischema_names.setdefault("vector", Vector)

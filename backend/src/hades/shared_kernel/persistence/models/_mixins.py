"""Reusable ORM column mixins.

Every table in Hades carries a UUIDv7 primary key and ``created_at`` /
``updated_at`` timestamps (a hard requirement of the schema design). These
mixins centralise that so no table can forget them and so the columns behave
identically everywhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from hades.shared_kernel.domain.identifiers import uuid7


class UUIDPrimaryKeyMixin:
    """A time-ordered UUIDv7 primary key named ``id``."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )


class TimestampMixin:
    """``created_at`` / ``updated_at`` maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

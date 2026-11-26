from sqlalchemy.orm import DeclarativeBase

from uuid import UUID, uuid4

from sqlalchemy import Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PublicIdMixin:
    """Provide an unguessable API-facing UUID alongside the internal integer key."""

    public_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid4,
        unique=True,
        index=True,
        nullable=False,
    )


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""

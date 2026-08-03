import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from lunora.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Thread(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "threads"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message_count: Mapped[int] = mapped_column(default=0)


class Message(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)

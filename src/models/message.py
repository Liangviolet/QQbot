"""GroupMessage ORM 模型 — 群消息持久化"""

from sqlalchemy import Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class GroupMessage(Base):
    __tablename__ = "group_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    plain_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)

    __table_args__ = (
        Index("idx_group_time", "group_id", "timestamp"),
        Index("idx_user_group", "user_id", "group_id"),
    )

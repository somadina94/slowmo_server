from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class QuizResponse(TimestampMixin, Base):
    __tablename__ = "quiz_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    answers: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(40), default="fit")

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WellnessProgram(TimestampMixin, Base):
    __tablename__ = "wellness_programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    duration: Mapped[str] = mapped_column(String(40))
    icon: Mapped[str] = mapped_column(String(8), default="")
    active: Mapped[bool] = mapped_column(default=True)

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Address(TimestampMixin, Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32))
    email: Mapped[str] = mapped_column(String(255), default="")
    line: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(80))
    pincode: Mapped[str] = mapped_column(String(12))
    state: Mapped[str] = mapped_column(String(80))
    is_default: Mapped[bool] = mapped_column(default=False)

    user = relationship("User", back_populates="addresses")

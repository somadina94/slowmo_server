from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Consult(TimestampMixin, Base):
    __tablename__ = "consults"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32))
    email: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text, default="")
    slot: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(24), default="scheduled")
    notes: Mapped[str] = mapped_column(Text, default="")

    order = relationship("Order", back_populates="consult")


class RxFile(TimestampMixin, Base):
    __tablename__ = "rx_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(24), default="pending_verify")

    order = relationship("Order", back_populates="rx_file")


class Prescription(TimestampMixin, Base):
    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    code: Mapped[str] = mapped_column(String(24), unique=True)
    dose: Mapped[str] = mapped_column(String(80), default="1/day, 45min before bed")
    duration: Mapped[str] = mapped_column(String(40), default="30 days")
    status: Mapped[str] = mapped_column(String(24), default="issued")

    order = relationship("Order", back_populates="prescription")

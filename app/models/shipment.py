from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Shipment(TimestampMixin, Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    stage: Mapped[str] = mapped_column(String(24), default="packed", index=True)
    awb: Mapped[str] = mapped_column(String(64), default="")
    carrier: Mapped[str] = mapped_column(String(40), default="stub")
    pickup_id: Mapped[str] = mapped_column(String(64), default="")

    order = relationship("Order", back_populates="shipment")
    events = relationship("ShipmentEvent", back_populates="shipment", cascade="all, delete-orphan")


class ShipmentEvent(TimestampMixin, Base):
    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    stage: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text, default="")

    shipment = relationship("Shipment", back_populates="events")

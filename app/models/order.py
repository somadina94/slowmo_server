from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utcnow


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="consult", index=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="cod")
    payment_status: Mapped[str] = mapped_column(String(16), default="cod")
    razorpay_order_id: Mapped[str] = mapped_column(String(64), default="")
    razorpay_payment_id: Mapped[str] = mapped_column(String(64), default="")
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    program_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    program_skipped: Mapped[bool] = mapped_column(default=False)
    age_confirmed: Mapped[bool] = mapped_column(default=False)
    ship_name: Mapped[str] = mapped_column(String(120))
    ship_phone: Mapped[str] = mapped_column(String(32))
    ship_email: Mapped[str] = mapped_column(String(255), default="")
    ship_address: Mapped[str] = mapped_column(Text)
    ship_city: Mapped[str] = mapped_column(String(80))
    ship_pincode: Mapped[str] = mapped_column(String(12))
    ship_state: Mapped[str] = mapped_column(String(80))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    consult = relationship("Consult", back_populates="order", uselist=False)
    rx_file = relationship("RxFile", back_populates="order", uselist=False)
    prescription = relationship("Prescription", back_populates="order", uselist=False)
    shipment = relationship("Shipment", back_populates="order", uselist=False)


class OrderItem(TimestampMixin, Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    sku: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)
    mrp: Mapped[int] = mapped_column(Integer)

    order = relationship("Order", back_populates="items")

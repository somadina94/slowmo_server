from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Sku(TimestampMixin, Base):
    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"), unique=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    allocated: Mapped[int] = mapped_column(Integer, default=0)
    weekly_forecast: Mapped[int] = mapped_column(Integer, default=0)

    variant = relationship("ProductVariant", back_populates="sku_record")
    batches = relationship("Batch", back_populates="sku")
    movements = relationship("InventoryMovement", back_populates="sku")


class Batch(TimestampMixin, Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    made_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    qty: Mapped[int] = mapped_column(Integer)

    sku = relationship("Sku", back_populates="batches")


class InventoryMovement(TimestampMixin, Base):
    __tablename__ = "inventory_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    qty: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")

    sku = relationship("Sku", back_populates="movements")

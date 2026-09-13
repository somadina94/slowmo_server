from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    flavor: Mapped[str] = mapped_column(String(80), default="Mixed berry")
    extract_mg: Mapped[str] = mapped_column(String(16), default="3.5mg")
    active: Mapped[bool] = mapped_column(default=True)

    variants = relationship("ProductVariant", back_populates="product")


class ProductVariant(TimestampMixin, Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)
    mrp: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(160), default="")
    active: Mapped[bool] = mapped_column(default=True)

    product = relationship("Product", back_populates="variants")
    sku_record = relationship("Sku", back_populates="variant", uselist=False)

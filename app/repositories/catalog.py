from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product, ProductVariant
from app.models.program import WellnessProgram


def list_products(db: Session, active_only: bool = True) -> list[Product]:
    stmt = select(Product).options(selectinload(Product.variants))
    if active_only:
        stmt = stmt.where(Product.active.is_(True))
    return list(db.scalars(stmt))


def get_variant_by_sku(db: Session, sku: str) -> ProductVariant | None:
    return db.scalar(select(ProductVariant).where(ProductVariant.sku == sku))


def list_programs(db: Session, active_only: bool = True) -> list[WellnessProgram]:
    stmt = select(WellnessProgram)
    if active_only:
        stmt = stmt.where(WellnessProgram.active.is_(True))
    return list(db.scalars(stmt))


def get_program(db: Session, key: str) -> WellnessProgram | None:
    return db.scalar(select(WellnessProgram).where(WellnessProgram.key == key))

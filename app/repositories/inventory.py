from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import Batch, InventoryMovement, Sku


def get_sku(db: Session, code: str) -> Sku | None:
    return db.scalar(select(Sku).where(Sku.code == code))


def list_skus(db: Session) -> list[Sku]:
    return list(db.scalars(select(Sku).order_by(Sku.id)))


def add_sku(db: Session, sku: Sku) -> Sku:
    db.add(sku)
    db.flush()
    return sku


def list_batches(db: Session) -> list[Batch]:
    return list(db.scalars(select(Batch).order_by(Batch.id)))


def add_movement(db: Session, movement: InventoryMovement) -> InventoryMovement:
    db.add(movement)
    db.flush()
    return movement


def add_batch(db: Session, batch: Batch) -> Batch:
    db.add(batch)
    db.flush()
    return batch

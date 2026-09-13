from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.inventory import Batch, InventoryMovement
from app.repositories import inventory as inv_repo
from app.services.ids import days_of_cover, stock_level


def allocate(db: Session, sku_code: str, qty: int) -> None:
    sku = inv_repo.get_sku(db, sku_code)
    if sku is None:
        raise NotFoundError("SKU not found")
    available = sku.stock - sku.allocated
    if available < qty:
        raise ValidationAppError("Insufficient inventory")
    sku.allocated += qty
    inv_repo.add_movement(db, InventoryMovement(sku_id=sku.id, kind="allocate", qty=qty, note="order allocate"))


def deallocate(db: Session, sku_code: str, qty: int) -> None:
    sku = inv_repo.get_sku(db, sku_code)
    if sku is None:
        raise NotFoundError("SKU not found")
    sku.allocated = max(sku.allocated - qty, 0)
    inv_repo.add_movement(db, InventoryMovement(sku_id=sku.id, kind="deallocate", qty=qty, note="order release"))


def receive(db: Session, sku_code: str, qty: int, note: str, batch_code: str | None = None) -> dict:
    sku = inv_repo.get_sku(db, sku_code)
    if sku is None:
        raise NotFoundError("SKU not found")
    if qty <= 0:
        raise ValidationAppError("Quantity must be positive")
    sku.stock += qty
    inv_repo.add_movement(db, InventoryMovement(sku_id=sku.id, kind="receipt", qty=qty, note=note))
    if batch_code:
        today = date.today()
        inv_repo.add_batch(
            db,
            Batch(sku_id=sku.id, code=batch_code, made_on=today, expires_on=today + timedelta(days=365), qty=qty),
        )
    return snapshot(db)


def snapshot(db: Session) -> dict:
    skus = []
    for sku in inv_repo.list_skus(db):
        level = stock_level(sku.stock, sku.allocated, sku.weekly_forecast)
        skus.append(
            {
                "name": sku.name,
                "sku": sku.code,
                "stock": sku.stock,
                "allocated": sku.allocated,
                "forecast": sku.weekly_forecast,
                "level": level,
                "days": days_of_cover(sku.stock, sku.allocated, sku.weekly_forecast),
            }
        )
    batches = [
        {
            "b": batch.code,
            "made": batch.made_on.strftime("%b %d %Y"),
            "exp": batch.expires_on.strftime("%b %d %Y"),
            "qty": batch.qty,
        }
        for batch in inv_repo.list_batches(db)
    ]
    min_days = min((row["days"] for row in skus), default=0)
    return {
        "skus": skus,
        "batches": batches,
        "warehouse": "Bengaluru",
        "days_remaining": min_days,
        "next_batch_due": (date.today() + timedelta(days=12)).strftime("%b %d"),
    }

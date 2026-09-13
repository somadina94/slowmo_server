from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.inventory import Batch, InventoryMovement, Sku
from app.models.product import Product, ProductVariant
from app.repositories import catalog as catalog_repo
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


def create_sku(
    db: Session,
    *,
    code: str,
    name: str,
    pack_qty: int,
    price: int,
    mrp: int,
    label: str = "",
    description: str = "",
    stock: int = 0,
    weekly_forecast: int = 0,
) -> dict:
    sku_code = code.strip().upper()
    display = name.strip()
    if not sku_code or not display:
        raise ValidationAppError("SKU code and name are required")
    if pack_qty <= 0 or price < 0 or mrp < 0 or stock < 0 or weekly_forecast < 0:
        raise ValidationAppError("Invalid quantity or price values")
    if mrp < price:
        raise ValidationAppError("MRP must be greater than or equal to price")
    if inv_repo.get_sku(db, sku_code) is not None or catalog_repo.get_variant_by_sku(db, sku_code) is not None:
        raise ConflictError("SKU already exists")

    product = catalog_repo.get_default_product(db)
    if product is None:
        product = catalog_repo.add_product(
            db,
            Product(
                slug="slow-mo-gummies",
                name="Slow Mo wellness gummies",
                description="Mixed-berry gummies · 3.5mg Vijaya extract each · Ayurvedic proprietary medicine, prescription use only.",
            ),
        )

    variant = catalog_repo.add_variant(
        db,
        ProductVariant(
            product_id=product.id,
            sku=sku_code,
            qty=pack_qty,
            price=price,
            mrp=mrp,
            label=label.strip() or f"{pack_qty} pack",
            description=description.strip(),
        ),
    )
    inv_repo.add_sku(
        db,
        Sku(
            variant_id=variant.id,
            code=sku_code,
            name=display,
            stock=stock,
            allocated=0,
            weekly_forecast=weekly_forecast,
        ),
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

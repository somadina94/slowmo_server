from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.order import Order
from app.models.shipment import Shipment


def _eager():
    return (
        selectinload(Order.items),
        selectinload(Order.consult),
        selectinload(Order.rx_file),
        selectinload(Order.prescription),
        selectinload(Order.shipment).selectinload(Shipment.events),
    )


def get_by_public_id(db: Session, public_id: str) -> Order | None:
    return db.scalar(select(Order).options(*_eager()).where(Order.public_id == public_id))


def get_by_id(db: Session, order_id: int) -> Order | None:
    return db.scalar(select(Order).options(*_eager()).where(Order.id == order_id))


def get_by_razorpay(db: Session, razorpay_order_id: str) -> Order | None:
    return db.scalar(select(Order).options(*_eager()).where(Order.razorpay_order_id == razorpay_order_id))


def list_for_user(db: Session, user_id: int) -> list[Order]:
    return list(db.scalars(select(Order).options(*_eager()).where(Order.user_id == user_id).order_by(Order.id.desc())))


def list_all(db: Session, status: str | None = None, search: str = "") -> list[Order]:
    stmt = select(Order).options(*_eager())
    if status and status != "all":
        stmt = stmt.where(Order.status == status)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Order.public_id.ilike(like) | Order.ship_name.ilike(like) | Order.ship_city.ilike(like))
    return list(db.scalars(stmt.order_by(Order.id.desc())))


def add(db: Session, order: Order) -> Order:
    db.add(order)
    db.flush()
    return order

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.integrations.notifications import Notifier
from app.integrations.razorpay import RazorpayGateway
from app.models.consult import Consult, RxFile
from app.models.order import Order, OrderItem
from app.repositories import audit as audit_repo
from app.repositories import catalog as catalog_repo
from app.repositories import orders as order_repo
from app.schemas.orders import (
    ConsultOut,
    OrderCreate,
    OrderItemOut,
    OrderOut,
    PrescriptionOut,
    RazorpayPayload,
    RxFileOut,
    ShipmentEventOut,
    ShipmentOut,
)
from app.services import inventory as inventory_service
from app.services.ids import allowed_order_transition, make_order_id


def serialize_order(order: Order, razorpay: RazorpayPayload | None = None) -> OrderOut:
    return OrderOut(
        id=order.id,
        public_id=order.public_id,
        status=order.status,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        total=order.total,
        subtotal=order.subtotal,
        discount=order.discount,
        program_key=order.program_key,
        program_skipped=order.program_skipped,
        ship_name=order.ship_name,
        ship_phone=order.ship_phone,
        ship_email=order.ship_email,
        ship_address=order.ship_address,
        ship_city=order.ship_city,
        ship_pincode=order.ship_pincode,
        ship_state=order.ship_state,
        placed_at=order.placed_at.isoformat(),
        items=[OrderItemOut.model_validate(item) for item in order.items],
        consult=ConsultOut.model_validate(order.consult) if order.consult else None,
        rx_file=RxFileOut.model_validate(order.rx_file) if order.rx_file else None,
        prescription=PrescriptionOut.model_validate(order.prescription) if order.prescription else None,
        shipment=_serialize_shipment(order),
        age_confirmed=order.age_confirmed,
        razorpay_order_id=order.razorpay_order_id,
        razorpay_payment_id=order.razorpay_payment_id,
        razorpay=razorpay,
    )


def _serialize_shipment(order: Order) -> ShipmentOut | None:
    if order.shipment is None:
        return None
    return ShipmentOut(
        stage=order.shipment.stage,
        awb=order.shipment.awb,
        carrier=order.shipment.carrier,
        pickup_id=order.shipment.pickup_id,
        events=[
            ShipmentEventOut(stage=event.stage, note=event.note, created_at=event.created_at.isoformat())
            for event in order.shipment.events
        ],
    )


def next_public_id(db, maker=make_order_id) -> str:
    public_id = maker()
    while order_repo.get_by_public_id(db, public_id):
        public_id = maker()
    return public_id


def create_order(
    db: Session,
    settings: Settings,
    user_id: int,
    payload: OrderCreate,
    gateway: RazorpayGateway,
    notifier: Notifier,
) -> OrderOut:
    if not payload.age_confirmed:
        raise ValidationAppError("You must confirm you are 21+")
    if payload.consult is None and payload.rx_file_id is None:
        raise ValidationAppError("Consult or prescription is required")
    if payload.program_key and not payload.program_skipped:
        program = catalog_repo.get_program(db, payload.program_key)
        if program is None:
            raise ValidationAppError("Unknown wellness program")
    elif payload.program_key and payload.program_skipped:
        raise ValidationAppError("Cannot skip and select a program")
    variant = catalog_repo.get_variant_by_sku(db, payload.sku)
    if variant is None or not variant.active:
        raise NotFoundError("Product variant not found")

    public_id = next_public_id(db)
    prepaid = payload.payment == "prepaid"
    order = Order(
        public_id=public_id,
        user_id=user_id,
        status="pending_payment" if prepaid else "consult",
        payment_method=payload.payment,
        payment_status="pending" if prepaid else "cod",
        subtotal=variant.mrp,
        discount=variant.mrp - variant.price,
        total=variant.price,
        program_key=None if payload.program_skipped else payload.program_key,
        program_skipped=payload.program_skipped,
        age_confirmed=True,
        ship_name=payload.address.name,
        ship_phone=payload.address.phone,
        ship_email=payload.address.email,
        ship_address=payload.address.line,
        ship_city=payload.address.city,
        ship_pincode=payload.address.pincode,
        ship_state=payload.address.state,
        placed_at=datetime.now(timezone.utc),
    )
    order.items.append(
        OrderItem(sku=variant.sku, name=f"Slow Mo Gummies · {variant.qty} pack", qty=variant.qty, price=variant.price, mrp=variant.mrp)
    )
    if payload.consult:
        order.consult = Consult(
            name=payload.consult.name,
            phone=payload.consult.phone,
            email=payload.consult.email,
            reason=payload.consult.reason,
            slot=payload.consult.slot,
        )
    if payload.rx_file_id:
        rx = db.get(RxFile, payload.rx_file_id)
        if rx is None or rx.user_id != user_id:
            raise NotFoundError("Prescription file not found")
        rx.order = order
        order.rx_file = rx

    razorpay_payload = None
    if prepaid:
        created = gateway.create_order(variant.price * 100, public_id)
        order.razorpay_order_id = created.id
        razorpay_payload = RazorpayPayload(
            order_id=created.id, amount=created.amount, currency=created.currency, key_id=settings.razorpay_key_id
        )
    else:
        inventory_service.allocate(db, variant.sku, 1)

    order_repo.add(db, order)
    audit_repo.write(db, user_id, "order.create", "order", public_id, payload.payment)
    if not prepaid:
        notifier.order_placed(order.ship_email, order.ship_phone, public_id, order.ship_name)
    return serialize_order(order, razorpay_payload)


def get_order(db: Session, public_id: str, user_id: int, staff: bool) -> OrderOut:
    order = order_repo.get_by_public_id(db, public_id)
    if order is None:
        raise NotFoundError("Order not found")
    if not staff and order.user_id != user_id:
        raise ForbiddenError("Not your order")
    return serialize_order(order)


def list_mine(db: Session, user_id: int) -> list[OrderOut]:
    return [serialize_order(order) for order in order_repo.list_for_user(db, user_id)]


def mark_paid(db: Session, order: Order, payment_id: str, notifier: Notifier) -> Order:
    if order.status != "pending_payment":
        raise ValidationAppError("Order is not awaiting payment")
    item = order.items[0]
    inventory_service.allocate(db, item.sku, 1)
    order.payment_status = "paid"
    order.status = "consult"
    order.razorpay_payment_id = payment_id
    notifier.order_paid(order.ship_email, order.public_id, order.ship_name)
    return order


def transition(db: Session, public_id: str, nxt: str, actor_id: int, notifier: Notifier | None = None) -> OrderOut:
    order = order_repo.get_by_public_id(db, public_id)
    if order is None:
        raise NotFoundError("Order not found")
    if not allowed_order_transition(order.status, nxt):
        raise ValidationAppError(f"Cannot move from {order.status} to {nxt}")
    if nxt == "cancelled" and order.status in {"consult", "pending_payment", "confirmed", "hold"}:
        if order.payment_status in {"cod", "paid"} and order.status != "pending_payment":
            inventory_service.deallocate(db, order.items[0].sku, 1)
    order.status = nxt
    audit_repo.write(db, actor_id, "order.status", "order", public_id, nxt)
    if notifier is not None:
        notifier.order_status(order.ship_email, order.public_id, nxt, order.ship_name)
    return serialize_order(order)

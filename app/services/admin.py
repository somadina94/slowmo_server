from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.integrations.notifications import Notifier
from app.integrations.shipping import ShippingProvider
from app.models.consult import Prescription
from app.models.order import Order
from app.models.shipment import Shipment, ShipmentEvent
from app.models.user import User
from app.repositories import audit as audit_repo
from app.repositories import orders as order_repo
from app.repositories import users as user_repo
from app.services.ids import allowed_shipment_transition, format_inr, greeting_for_hour, make_rx_code
from app.services.inventory import snapshot as inventory_snapshot


STATUS_LABEL = {
    "consult": "Pending consult",
    "confirmed": "Confirmed",
    "dispatched": "Dispatched",
    "delivered": "Delivered",
    "hold": "On hold",
    "pending_payment": "Pending payment",
    "cancelled": "Cancelled",
}


def _order_row(order: Order) -> dict:
    return {
        "id": order.public_id,
        "name": order.ship_name,
        "city": order.ship_city,
        "qty": order.items[0].qty if order.items else 0,
        "total": order.total,
        "status": order.status,
        "pay": order.payment_method.upper() if order.payment_method == "cod" else "PREPAID",
        "placed": order.placed_at.strftime("%d %b · %I:%M %p"),
        "label": STATUS_LABEL.get(order.status, order.status),
    }


def overview(db: Session, staff: User, now: datetime | None = None) -> dict:
    moment = now or datetime.now(timezone.utc)
    orders = order_repo.list_all(db)
    paid = [order for order in orders if order.status not in {"pending_payment", "cancelled"}]
    consults = [order for order in paid if order.status == "consult"]
    revenue = sum(order.total for order in paid)
    aov = int(revenue / len(paid)) if paid else 0
    greeting = greeting_for_hour(moment.hour)
    cities = Counter(order.ship_city for order in paid)
    top = cities.most_common(7)
    max_n = top[0][1] if top else 1
    return {
        "greeting": f"{greeting}, {staff.name.split()[0]}.",
        "datetime": moment.strftime("%a %d %b · %I:%M %p"),
        "pending_consults": len(consults),
        "pending_confirmations": len(consults),
        "kpis": [
            {"label": "Preorders (7d)", "value": str(len(paid)), "delta": "+0%", "type": "up"},
            {"label": "Consults booked", "value": str(len(consults)), "delta": "+0%", "type": "up"},
            {"label": "COD success rate", "value": "100%" if paid else "0%", "delta": "+0%", "type": "up"},
            {"label": "Avg order value", "value": f"₹{aov:,}", "delta": "+0%", "type": "up"},
        ],
        "revenue": {
            "value": format_inr(revenue),
            "delta": "lifetime",
            "type": "flat",
            "orders": len(paid),
            "aov": f"₹{aov:,}",
            "label": "Lifetime",
            "chart": [order.total for order in paid[-14:]] or [0],
        },
        "geo": [
            {"city": city, "i": city[:2].upper(), "n": count, "pct": int(count / max_n * 100)}
            for city, count in top
        ],
        "recent": [_order_row(order) for order in paid[:5]],
    }


def orders_page(db: Session, status: str = "all", search: str = "") -> dict:
    rows = [_order_row(order) for order in order_repo.list_all(db, status=status, search=search)]
    return {"orders": rows, "count": len(rows)}


def consults_page(db: Session) -> dict:
    # Call queue: booked consults still open on unpaid-or-consult orders.
    # RX-only preorders never create a Consult row — those land in pending_rx.
    cards = []
    pending_rx = []
    rxs = []
    for order in order_repo.list_all(db):
        if (
            order.consult
            and order.consult.status == "scheduled"
            and order.status in {"consult", "pending_payment", "hold"}
        ):
            cards.append(
                {
                    "id": order.public_id,
                    "name": order.consult.name,
                    "phone": order.consult.phone,
                    "time": order.consult.slot or "Within 24 hrs",
                    "date": "Today",
                    "note": order.consult.reason or "No intake note",
                    "order_status": order.status,
                }
            )
        if order.rx_file and order.rx_file.status == "pending_verify":
            pending_rx.append(
                {
                    "id": order.public_id,
                    "name": order.ship_name,
                    "file": order.rx_file.filename,
                    "status": order.rx_file.status,
                }
            )
        if order.prescription:
            rxs.append(
                {
                    "id": order.public_id,
                    "name": order.ship_name,
                    "rx": order.prescription.code,
                    "dose": order.prescription.dose,
                    "dur": order.prescription.duration,
                    "status": order.prescription.status.title(),
                }
            )
    return {
        "consults": cards,
        "pending_rx": pending_rx,
        "prescriptions": rxs,
        "remaining": len(cards),
    }


def complete_consult(db: Session, public_id: str, actor_id: int, notes: str = "", notifier: Notifier | None = None) -> dict:
    order = order_repo.get_by_public_id(db, public_id)
    if order is None or order.consult is None:
        raise NotFoundError("Consult not found")
    order.consult.status = "completed"
    order.consult.notes = notes
    if order.status == "consult":
        order.status = "confirmed"
    if order.prescription is None:
        order.prescription = Prescription(code=make_rx_code(order.public_id))
    audit_repo.write(db, actor_id, "consult.complete", "consult", public_id, notes)
    if notifier is not None:
        notifier.consult_update(
            order.ship_email,
            order.public_id,
            "Your consult is complete and your order is confirmed.",
            order.ship_name,
        )
    return consults_page(db)


def reschedule_consult(
    db: Session,
    public_id: str,
    slot: str,
    actor_id: int,
    notifier: Notifier | None = None,
) -> dict:
    order = order_repo.get_by_public_id(db, public_id)
    if order is None or order.consult is None:
        raise NotFoundError("Consult not found")
    order.consult.slot = slot
    audit_repo.write(db, actor_id, "consult.reschedule", "consult", public_id, slot)
    if notifier is not None:
        notifier.consult_update(
            order.ship_email,
            order.public_id,
            f"Your consult was rescheduled to {slot}.",
            order.ship_name,
        )
    return consults_page(db)


def verify_rx(db: Session, public_id: str, actor_id: int, accept: bool, notifier: Notifier | None = None) -> dict:
    order = order_repo.get_by_public_id(db, public_id)
    if order is None or order.rx_file is None:
        raise NotFoundError("Prescription file not found")
    order.rx_file.status = "issued" if accept else "rejected"
    if accept:
        order.status = "confirmed"
        if order.prescription is None:
            order.prescription = Prescription(code=make_rx_code(order.public_id), status="issued")
    audit_repo.write(db, actor_id, "rx.verify", "rx", public_id, str(accept))
    if notifier is not None:
        notifier.rx_decision(order.ship_email, order.public_id, accept, order.ship_name)
    return consults_page(db)


def customers_page(db: Session, search: str = "") -> dict:
    users = user_repo.list_customers(db, search)
    rows = []
    for user in users:
        orders = [order for order in user.orders if order.status not in {"cancelled", "pending_payment"}]
        spent = sum(order.total for order in orders)
        program = next((order.program_key or "—" for order in orders if order.program_key), "—")
        rows.append(
            {
                "name": user.name,
                "email": user.email,
                "city": orders[0].ship_city if orders else "",
                "orders": len(orders),
                "spent": spent,
                "prog": program,
                "i": user.initials,
                "joined": user.created_at.strftime("%b %d") if user.created_at else "",
            }
        )
    enrolled = sum(1 for row in rows if row["prog"] not in {"—", None})
    return {"customers": rows, "total": len(rows), "enrolled": enrolled}


def analytics_page(db: Session) -> dict:
    orders = [order for order in order_repo.list_all(db) if order.status not in {"cancelled", "pending_payment"}]
    revenue = sum(order.total for order in orders)
    aov = int(revenue / len(orders)) if orders else 0
    states = Counter(order.ship_state for order in orders)
    max_state = max(states.values(), default=1)
    return {
        "kpis": [
            {"label": "Total revenue", "value": format_inr(revenue), "delta": "↑ 0%"},
            {"label": "Avg order value", "value": f"₹{aov:,}", "delta": "↑ 0%"},
            {"label": "Conversion rate", "value": "100%" if orders else "0%", "delta": "↑ 0pp"},
            {"label": "Repeat rate", "value": "0%", "delta": "0%"},
        ],
        "funnel": [
            {"label": "Landing visitors", "n": max(len(orders) * 10, 10), "pct": 100},
            {"label": "Order placed", "n": len(orders), "pct": 10 if orders else 0},
        ],
        "sources": [{"src": "Direct", "n": str(len(orders)), "pct": 100, "color": "#3E2A6E"}],
        "states": [{"s": name, "n": count, "pct": int(count / max_state * 100)} for name, count in states.most_common()],
    }


def counts(db: Session) -> dict:
    page = consults_page(db)
    orders = order_repo.list_all(db)
    return {
        "orders": len([order for order in orders if order.status == "consult"]),
        "consults": page["remaining"] + len(page["pending_rx"]),
    }


def dispatch_kanban(db: Session) -> dict:
    columns = {key: [] for key in ("packed", "picked", "transit", "delivered")}
    for order in order_repo.list_all(db):
        if order.shipment:
            columns[order.shipment.stage].append(
                {
                    "id": order.public_id,
                    "name": order.ship_name,
                    "city": order.ship_city,
                    "time": "1h",
                }
            )
    return {
        "columns": [
            {"key": key, "label": label, "cards": columns[key]}
            for key, label in (("packed", "Packed"), ("picked", "Picked up"), ("transit", "In transit"), ("delivered", "Delivered"))
        ],
        "carrier": "stub",
        "in_transit": len(columns["transit"]),
    }


def create_shipment(
    db: Session,
    public_id: str,
    actor_id: int,
    provider: ShippingProvider,
    notifier: Notifier | None = None,
) -> dict:
    order = order_repo.get_by_public_id(db, public_id)
    if order is None:
        raise NotFoundError("Order not found")
    if order.status not in {"confirmed", "dispatched"}:
        raise ValidationAppError("Order is not ready to ship")
    if order.shipment is None:
        result = provider.create_shipment(order.public_id, order.ship_city)
        order.shipment = Shipment(stage="packed", awb=result.awb, carrier=result.carrier)
        order.shipment.events.append(ShipmentEvent(stage="packed", note="created"))
        order.status = "dispatched"
        audit_repo.write(db, actor_id, "shipment.create", "shipment", public_id, result.awb)
        if notifier is not None:
            notifier.order_status(order.ship_email, order.public_id, "dispatched", order.ship_name)
    return dispatch_kanban(db)


def move_shipment(
    db: Session,
    public_id: str,
    stage: str,
    actor_id: int,
    provider: ShippingProvider,
    notifier: Notifier | None = None,
) -> dict:
    order = order_repo.get_by_public_id(db, public_id)
    if order is None or order.shipment is None:
        raise NotFoundError("Shipment not found")
    if not allowed_shipment_transition(order.shipment.stage, stage):
        raise ValidationAppError("Invalid shipment transition")
    order.shipment.stage = stage
    order.shipment.events.append(ShipmentEvent(stage=stage, note="moved"))
    if stage == "delivered":
        order.status = "delivered"
        provider.track(order.shipment.awb)
        if notifier is not None:
            notifier.order_status(order.ship_email, order.public_id, "delivered", order.ship_name)
    audit_repo.write(db, actor_id, "shipment.move", "shipment", public_id, stage)
    return dispatch_kanban(db)


def schedule_pickup(db: Session, public_id: str, actor_id: int, provider: ShippingProvider) -> dict:
    order = order_repo.get_by_public_id(db, public_id)
    if order is None or order.shipment is None:
        raise NotFoundError("Shipment not found")
    order.shipment.pickup_id = provider.schedule_pickup(order.shipment.awb)
    audit_repo.write(db, actor_id, "shipment.pickup", "shipment", public_id, order.shipment.pickup_id)
    return {"pickup_id": order.shipment.pickup_id}


def manifest(db: Session, provider: ShippingProvider) -> str:
    awbs = [order.shipment.awb for order in order_repo.list_all(db) if order.shipment and order.shipment.awb]
    return provider.manifest(awbs)


def export_orders_csv(db: Session) -> str:
    lines = ["id,name,city,total,status"]
    for order in order_repo.list_all(db):
        lines.append(f"{order.public_id},{order.ship_name},{order.ship_city},{order.total},{order.status}")
    return "\n".join(lines) + "\n"


def inventory_page(db: Session) -> dict:
    return inventory_snapshot(db)

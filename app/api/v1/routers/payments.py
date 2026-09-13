import json

from fastapi import APIRouter, Depends, Request

from app.core.deps import CurrentStaff, CurrentUser, DbDep, SettingsDep, get_gateway, get_notifier
from app.core.exceptions import RateLimitError, ValidationAppError
from app.core.rate_limit import limiter
from app.integrations.notifications import Notifier
from app.integrations.razorpay import RazorpayGateway
from app.repositories import audit as audit_repo
from app.repositories import orders as order_repo
from app.schemas.orders import OrderOut, PaymentVerify
from app.services import orders as order_service

router = APIRouter(tags=["payments"])


@router.post("/payments/razorpay/verify", response_model=OrderOut)
def verify_payment(
    payload: PaymentVerify,
    db: DbDep,
    user: CurrentUser,
    gateway: RazorpayGateway = Depends(get_gateway),
    notifier: Notifier = Depends(get_notifier),
) -> OrderOut:
    order = order_repo.get_by_public_id(db, payload.public_id)
    if order is None or order.user_id != user.id:
        raise ValidationAppError("Order not found")
    if not gateway.verify_payment(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        raise ValidationAppError("Invalid payment signature")
    order_service.mark_paid(db, order, payload.razorpay_payment_id, notifier)
    audit_repo.write(db, user.id, "payment.verify", "order", order.public_id, payload.razorpay_payment_id)
    db.commit()
    return order_service.serialize_order(order)


@router.get("/payments/razorpay/config")
def razorpay_config(settings: SettingsDep, staff: CurrentStaff) -> dict:
    return {
        "key_id": settings.razorpay_key_id,
        "webhook_url": settings.razorpay_webhook_url,
    }


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    gateway: RazorpayGateway = Depends(get_gateway),
    notifier: Notifier = Depends(get_notifier),
) -> dict:
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(f"wh:{ip}", settings.rate_limit_webhook):
        raise RateLimitError()
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not gateway.verify_webhook(body, signature):
        raise ValidationAppError("Invalid webhook signature")
    payload = json.loads(body.decode() or "{}")
    event = payload.get("event", "")
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id", "")
    payment_id = entity.get("id", "")
    if event == "payment.captured" and order_id:
        order = order_repo.get_by_razorpay(db, order_id)
        if order and order.status == "pending_payment":
            order_service.mark_paid(db, order, payment_id, notifier)
            audit_repo.write(db, None, "payment.webhook", "order", order.public_id, payment_id)
            db.commit()
    return {"ok": True, "event": event}

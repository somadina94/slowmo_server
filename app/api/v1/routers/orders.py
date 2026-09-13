from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, DbDep, SettingsDep, get_gateway, get_notifier
from app.integrations.notifications import Notifier
from app.integrations.razorpay import RazorpayGateway
from app.models.quiz import QuizResponse
from app.schemas.orders import OrderCreate, OrderOut, QuizIn
from app.services import orders as order_service

router = APIRouter(tags=["orders"])


@router.post("/orders", response_model=OrderOut)
def create_order(
    payload: OrderCreate,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUser,
    gateway: RazorpayGateway = Depends(get_gateway),
    notifier: Notifier = Depends(get_notifier),
) -> OrderOut:
    result = order_service.create_order(db, settings, user.id, payload, gateway, notifier)
    db.commit()
    return result


@router.get("/orders", response_model=list[OrderOut])
def my_orders(db: DbDep, user: CurrentUser) -> list[OrderOut]:
    return order_service.list_mine(db, user.id)


@router.get("/orders/{public_id}", response_model=OrderOut)
def get_order(public_id: str, db: DbDep, user: CurrentUser) -> OrderOut:
    from app.core.rbac import is_staff

    return order_service.get_order(db, public_id, user.id, is_staff(user.role))


@router.post("/quiz")
def quiz(payload: QuizIn, db: DbDep, user: CurrentUser) -> dict:
    row = QuizResponse(user_id=user.id, answers=str(payload.answers), result="fit")
    db.add(row)
    db.commit()
    return {"result": "fit", "message": "Slow Mo looks like a fit."}

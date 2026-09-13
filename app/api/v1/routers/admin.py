from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.core.deps import CurrentStaff, DbDep, get_notifier, get_shipper, require
from app.core.exceptions import ForbiddenError
from app.models.user import User
from app.integrations.notifications import Notifier
from app.integrations.shipping import ShippingProvider
from app.repositories import users as user_repo
from app.schemas.admin import (
    ConsultAction,
    DispatchStageUpdate,
    InventoryReceipt,
    RescheduleConsult,
    SkuCreate,
    StaffCreate,
    StaffRoleUpdate,
)
from app.schemas.auth import UserOut
from app.schemas.orders import StatusUpdate
from app.services import admin as admin_service
from app.services import auth as auth_service
from app.services import inventory as inventory_service
from app.services import orders as order_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/me", response_model=UserOut)
def admin_me(staff: CurrentStaff) -> UserOut:
    return UserOut.model_validate(staff)


@router.get("/counts")
def admin_counts(db: DbDep, staff: User = Depends(require("admin.read"))) -> dict:
    return admin_service.counts(db)


@router.get("/overview")
def admin_overview(db: DbDep, staff: User = Depends(require("admin.read"))) -> dict:
    return admin_service.overview(db, staff)


@router.get("/orders")
def admin_orders(
    db: DbDep,
    status: str = "all",
    search: str = "",
    staff: User = Depends(require("orders.read")),
) -> dict:
    return admin_service.orders_page(db, status, search)


@router.get("/orders/export")
def admin_orders_export(db: DbDep, staff: User = Depends(require("orders.read"))) -> PlainTextResponse:
    return PlainTextResponse(admin_service.export_orders_csv(db), media_type="text/csv")


@router.post("/orders/{public_id}/status")
def admin_order_status(
    public_id: str,
    payload: StatusUpdate,
    db: DbDep,
    staff: User = Depends(require("orders.write")),
    notifier: Notifier = Depends(get_notifier),
) -> dict:
    result = order_service.transition(db, public_id, payload.status, staff.id, notifier)
    db.commit()
    return result.model_dump()


@router.get("/consults")
def admin_consults(db: DbDep, staff: User = Depends(require("consults.read"))) -> dict:
    return admin_service.consults_page(db)


@router.post("/consults/{public_id}/complete")
def admin_complete_consult(
    public_id: str,
    payload: ConsultAction,
    db: DbDep,
    staff: User = Depends(require("consults.write")),
    notifier: Notifier = Depends(get_notifier),
) -> dict:
    result = admin_service.complete_consult(db, public_id, staff.id, payload.notes, notifier)
    db.commit()
    return result


@router.post("/consults/{public_id}/reschedule")
def admin_reschedule(
    public_id: str,
    payload: RescheduleConsult,
    db: DbDep,
    staff: User = Depends(require("consults.write")),
    notifier: Notifier = Depends(get_notifier),
) -> dict:
    result = admin_service.reschedule_consult(db, public_id, payload.slot, staff.id, notifier)
    db.commit()
    return result


@router.post("/consults/{public_id}/verify-rx")
def admin_verify_rx(
    public_id: str,
    db: DbDep,
    accept: bool = Query(True),
    staff: User = Depends(require("consults.write")),
    notifier: Notifier = Depends(get_notifier),
) -> dict:
    result = admin_service.verify_rx(db, public_id, staff.id, accept, notifier)
    db.commit()
    return result


@router.get("/customers")
def admin_customers(db: DbDep, search: str = "", staff: User = Depends(require("customers.read"))) -> dict:
    return admin_service.customers_page(db, search)


@router.get("/analytics")
def admin_analytics(db: DbDep, staff: User = Depends(require("analytics.read"))) -> dict:
    return admin_service.analytics_page(db)


@router.get("/inventory")
def admin_inventory(db: DbDep, staff: User = Depends(require("inventory.read"))) -> dict:
    return admin_service.inventory_page(db)


@router.post("/inventory/receipts")
def admin_receipt(
    payload: InventoryReceipt,
    db: DbDep,
    staff: User = Depends(require("inventory.write")),
) -> dict:
    result = inventory_service.receive(db, payload.sku, payload.qty, payload.note, payload.batch_code)
    db.commit()
    return result


@router.post("/inventory/skus")
def admin_create_sku(
    payload: SkuCreate,
    db: DbDep,
    staff: User = Depends(require("inventory.write")),
) -> dict:
    result = inventory_service.create_sku(
        db,
        code=payload.sku,
        name=payload.name,
        pack_qty=payload.pack_qty,
        price=payload.price,
        mrp=payload.mrp,
        label=payload.label,
        description=payload.description,
        stock=payload.stock,
        weekly_forecast=payload.weekly_forecast,
    )
    db.commit()
    return result


@router.get("/dispatch")
def admin_dispatch(db: DbDep, staff: User = Depends(require("dispatch.read"))) -> dict:
    return admin_service.dispatch_kanban(db)


@router.post("/dispatch/{public_id}")
def admin_create_shipment(
    public_id: str,
    db: DbDep,
    staff: User = Depends(require("dispatch.write")),
    provider: ShippingProvider = Depends(get_shipper),
    notifier: Notifier = Depends(get_notifier),
) -> dict:
    result = admin_service.create_shipment(db, public_id, staff.id, provider, notifier)
    db.commit()
    return result


@router.patch("/dispatch/{public_id}")
def admin_move_shipment(
    public_id: str,
    payload: DispatchStageUpdate,
    db: DbDep,
    staff: User = Depends(require("dispatch.write")),
    provider: ShippingProvider = Depends(get_shipper),
    notifier: Notifier = Depends(get_notifier),
) -> dict:
    result = admin_service.move_shipment(db, public_id, payload.stage, staff.id, provider, notifier)
    db.commit()
    return result


@router.post("/dispatch/{public_id}/pickup")
def admin_pickup(
    public_id: str,
    db: DbDep,
    staff: User = Depends(require("dispatch.write")),
    provider: ShippingProvider = Depends(get_shipper),
) -> dict:
    result = admin_service.schedule_pickup(db, public_id, staff.id, provider)
    db.commit()
    return result


@router.get("/dispatch/manifest")
def admin_manifest(
    db: DbDep,
    staff: User = Depends(require("dispatch.read")),
    provider: ShippingProvider = Depends(get_shipper),
) -> PlainTextResponse:
    return PlainTextResponse(admin_service.manifest(db, provider), media_type="text/csv")


@router.get("/staff", response_model=list[UserOut])
def admin_list_staff(db: DbDep, staff: User = Depends(require("admin.users"))) -> list[UserOut]:
    return [UserOut.model_validate(row) for row in user_repo.list_staff(db)]


@router.post("/staff", response_model=UserOut)
def admin_create_staff(
    payload: StaffCreate,
    db: DbDep,
    staff: User = Depends(require("admin.users")),
) -> UserOut:
    if payload.role == "founder" and staff.role != "founder":
        raise ForbiddenError("Only a founder can create another founder")
    user = auth_service.create_staff(db, payload.email, payload.password, payload.name, payload.role, payload.phone)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/staff/{user_id}/role", response_model=UserOut)
def admin_update_staff_role(
    user_id: int,
    payload: StaffRoleUpdate,
    db: DbDep,
    staff: User = Depends(require("admin.users")),
) -> UserOut:
    user = auth_service.update_role(db, user_id, payload.role, staff)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)

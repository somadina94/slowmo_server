from pydantic import BaseModel


class ConsultAction(BaseModel):
    notes: str = ""


class RescheduleConsult(BaseModel):
    slot: str


class IssuePrescription(BaseModel):
    dose: str = "1/day, 45min before bed"
    duration: str = "30 days"


class DispatchStageUpdate(BaseModel):
    stage: str


class InventoryReceipt(BaseModel):
    sku: str
    qty: int
    note: str = "manual receipt"
    batch_code: str | None = None


class SkuCreate(BaseModel):
    sku: str
    name: str
    pack_qty: int
    price: int
    mrp: int
    label: str = ""
    description: str = ""
    stock: int = 0
    weekly_forecast: int = 0


class StaffCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str
    phone: str = ""

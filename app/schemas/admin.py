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


class StaffCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str
    phone: str = ""

from pydantic import BaseModel, EmailStr, Field


class ConsultIn(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    email: EmailStr
    reason: str = ""
    slot: str = ""


class AddressIn(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    email: str = ""
    line: str = Field(min_length=1)
    city: str = Field(min_length=1)
    pincode: str = Field(min_length=1)
    state: str = Field(min_length=1)


class OrderCreate(BaseModel):
    sku: str
    program_key: str | None = None
    program_skipped: bool = False
    consult: ConsultIn | None = None
    rx_file_id: int | None = None
    address: AddressIn
    payment: str = Field(pattern="^(cod|prepaid)$")
    age_confirmed: bool


class OrderItemOut(BaseModel):
    sku: str
    name: str
    qty: int
    price: int
    mrp: int

    model_config = {"from_attributes": True}


class ConsultOut(BaseModel):
    name: str
    phone: str
    email: str
    reason: str
    slot: str
    status: str
    notes: str = ""

    model_config = {"from_attributes": True}


class RxFileOut(BaseModel):
    id: int
    filename: str
    mime: str
    size: int
    status: str

    model_config = {"from_attributes": True}


class RazorpayPayload(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str


class PrescriptionOut(BaseModel):
    code: str
    dose: str
    duration: str
    status: str

    model_config = {"from_attributes": True}


class ShipmentEventOut(BaseModel):
    stage: str
    note: str
    created_at: str


class ShipmentOut(BaseModel):
    stage: str
    awb: str
    carrier: str
    pickup_id: str
    events: list[ShipmentEventOut] = []


class OrderOut(BaseModel):
    id: int
    public_id: str
    status: str
    payment_method: str
    payment_status: str
    total: int
    subtotal: int
    discount: int
    program_key: str | None
    program_skipped: bool
    age_confirmed: bool = False
    razorpay_order_id: str = ""
    razorpay_payment_id: str = ""
    ship_name: str
    ship_phone: str
    ship_email: str
    ship_address: str
    ship_city: str
    ship_pincode: str
    ship_state: str
    placed_at: str
    items: list[OrderItemOut]
    consult: ConsultOut | None = None
    rx_file: RxFileOut | None = None
    prescription: PrescriptionOut | None = None
    shipment: ShipmentOut | None = None
    razorpay: RazorpayPayload | None = None

    model_config = {"from_attributes": True}


class PaymentVerify(BaseModel):
    public_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class StatusUpdate(BaseModel):
    status: str


class QuizIn(BaseModel):
    answers: list[list[int]]

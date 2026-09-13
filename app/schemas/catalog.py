from pydantic import BaseModel, Field


class VariantOut(BaseModel):
    id: int
    sku: str
    qty: int
    price: int
    mrp: int
    label: str
    description: str
    active: bool

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    slug: str
    name: str
    description: str
    flavor: str
    extract_mg: str
    active: bool
    variants: list[VariantOut]

    model_config = {"from_attributes": True}


class VariantUpdate(BaseModel):
    price: int | None = Field(default=None, ge=0)
    mrp: int | None = Field(default=None, ge=0)
    label: str | None = None
    description: str | None = None
    active: bool | None = None


class ProgramOut(BaseModel):
    id: int
    key: str
    name: str
    description: str
    duration: str
    icon: str
    active: bool

    model_config = {"from_attributes": True}

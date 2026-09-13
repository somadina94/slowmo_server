from fastapi import APIRouter, Depends

from app.core.deps import DbDep, require
from app.models.user import User
from app.core.exceptions import NotFoundError
from app.repositories import catalog as catalog_repo
from app.schemas.catalog import ProductOut, ProgramOut, VariantUpdate

router = APIRouter(tags=["catalog"])


@router.get("/products", response_model=list[ProductOut])
def products(db: DbDep) -> list[ProductOut]:
    return [ProductOut.model_validate(item) for item in catalog_repo.list_products(db)]


@router.get("/programs", response_model=list[ProgramOut])
def programs(db: DbDep) -> list[ProgramOut]:
    return [ProgramOut.model_validate(item) for item in catalog_repo.list_programs(db)]


@router.patch("/admin/products/{sku}", response_model=ProductOut)
def update_variant(
    sku: str,
    payload: VariantUpdate,
    db: DbDep,
    staff: User = Depends(require("products.write")),
) -> ProductOut:
    variant = catalog_repo.get_variant_by_sku(db, sku)
    if variant is None:
        raise NotFoundError("Variant not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(variant, key, value)
    db.commit()
    db.refresh(variant.product)
    return ProductOut.model_validate(variant.product)

from fastapi import APIRouter

from app.api.v1.routers import admin, auth, catalog, files, orders, payments

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(catalog.router)
api_router.include_router(orders.router)
api_router.include_router(files.router)
api_router.include_router(payments.router)
api_router.include_router(admin.router)

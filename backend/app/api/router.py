from fastapi import APIRouter

from app.api.routes import auth, kitchen, menu, orders, reception, sales, tables


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(menu.router)
api_router.include_router(tables.router)
api_router.include_router(orders.router)
api_router.include_router(kitchen.router)
api_router.include_router(reception.router)
api_router.include_router(sales.router)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.order import KitchenStatusUpdateRequest
from app.schemas.table import TableDetail
from app.services.order_service import (
    ensure_item_belongs_to_order,
    list_active_kitchen_tables,
    load_order,
    serialize_table,
    update_kitchen_status,
)
from app.websockets.manager import manager


router = APIRouter(prefix="/kitchen", tags=["kitchen"])


@router.get("/active", response_model=list[TableDetail])
def get_active_kitchen_orders(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.KITCHEN, UserRole.RECEPTIONIST, UserRole.WAITER)),
):
    return [serialize_table(table, kitchen_view=True) for table in list_active_kitchen_tables(db)]


@router.patch("/orders/{order_id}/items/{item_id}/status", response_model=dict)
async def change_kitchen_status(
    order_id: int,
    item_id: int,
    payload: KitchenStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.KITCHEN)),
):
    order = load_order(db, order_id)
    item = ensure_item_belongs_to_order(order, item_id)
    update_kitchen_status(db, order, item, payload.kitchen_status, current_user)
    db.commit()
    order = load_order(db, order_id)
    await manager.broadcast(
        "kitchen_status_changed",
        {
            "table_id": order.table.id,
            "order_id": order.id,
            "item_id": item.id,
            "kitchen_status": payload.kitchen_status.value,
        },
    )
    return serialize_table(order.table, kitchen_view=True)


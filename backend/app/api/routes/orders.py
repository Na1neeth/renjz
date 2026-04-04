from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.order import (
    KitchenStatusUpdateRequest,
    OrderItemCreate,
    OrderItemUpdate,
    OrderRead,
    OrderStatusUpdateRequest,
)
from app.services.order_service import (
    add_item_to_order,
    cancel_order_item,
    ensure_item_belongs_to_order,
    find_order_item,
    load_order,
    serialize_order,
    update_kitchen_status,
    update_order_item,
    update_order_status,
)
from app.websockets.manager import manager


router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    order = load_order(db, order_id)
    return serialize_order(order)


@router.get("/{order_id}/history", response_model=list[dict])
def get_order_history(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    order = load_order(db, order_id)
    return serialize_order(order)["activity_log"]


@router.post("/{order_id}/items", response_model=OrderRead)
async def add_order_item(
    order_id: int,
    payload: OrderItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.WAITER)),
):
    order = load_order(db, order_id)
    item = add_item_to_order(
        db,
        order,
        item_name=payload.item_name,
        quantity=payload.quantity,
        note=payload.note,
        actor=current_user,
    )
    db.commit()
    order = load_order(db, order_id)
    await manager.broadcast(
        "item_added",
        {
            "table_id": order.table.id,
            "order_id": order.id,
            "item_id": item.id,
            "table_status": order.table.status.value,
        },
    )
    return serialize_order(order)


@router.patch("/{order_id}/items/{item_id}", response_model=OrderRead)
async def edit_order_item(
    order_id: int,
    item_id: int,
    payload: OrderItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.WAITER)),
):
    order = load_order(db, order_id)
    item = ensure_item_belongs_to_order(order, item_id)
    update_order_item(
        db,
        order,
        item,
        item_name=payload.item_name,
        quantity=payload.quantity,
        note=payload.note,
        actor=current_user,
    )
    db.commit()
    order = load_order(db, order_id)
    item = find_order_item(db, order, item_id)
    await manager.broadcast(
        "item_updated",
        {
            "table_id": order.table.id,
            "order_id": order.id,
            "item_id": item.id,
            "table_status": order.table.status.value,
        },
    )
    return serialize_order(order)


@router.post("/{order_id}/items/{item_id}/cancel", response_model=OrderRead)
async def cancel_item(
    order_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.WAITER)),
):
    order = load_order(db, order_id)
    item = ensure_item_belongs_to_order(order, item_id)
    cancel_order_item(db, order, item, current_user)
    db.commit()
    order = load_order(db, order_id)
    await manager.broadcast(
        "item_cancelled",
        {
            "table_id": order.table.id,
            "order_id": order.id,
            "item_id": item.id,
            "table_status": order.table.status.value,
        },
    )
    return serialize_order(order)


@router.patch("/{order_id}/status", response_model=OrderRead)
async def change_order_status(
    order_id: int,
    payload: OrderStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.WAITER)),
):
    order = load_order(db, order_id)
    update_order_status(db, order, payload.status, current_user)
    db.commit()
    order = load_order(db, order_id)
    await manager.broadcast(
        "order_status_changed",
        {
            "table_id": order.table.id,
            "order_id": order.id,
            "table_status": order.table.status.value,
            "order_status": order.status.value,
        },
    )
    return serialize_order(order)

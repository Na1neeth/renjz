from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.billing_item import BillingItem
from app.models.enums import (
    ActivityAction,
    KitchenItemStatus,
    OrderItemStatus,
    OrderStatus,
    TableStatus,
)
from app.models.order import Order
from app.models.order_activity_log import OrderActivityLog
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.table import RestaurantTable
from app.models.user import User


ACTIVE_ORDER_STATUSES = (OrderStatus.RUNNING,)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_table(db: Session, table_id: int) -> RestaurantTable:
    table = db.scalar(
        select(RestaurantTable)
        .where(RestaurantTable.id == table_id)
        .options(
            selectinload(RestaurantTable.orders)
            .selectinload(Order.items),
            selectinload(RestaurantTable.orders)
            .selectinload(Order.activities),
            selectinload(RestaurantTable.orders)
            .selectinload(Order.payments),
        )
    )
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


def load_order(db: Session, order_id: int) -> Order:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.table),
            selectinload(Order.items),
            selectinload(Order.activities),
            selectinload(Order.billing_items),
            selectinload(Order.payments),
        )
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def get_active_order_for_table(table: RestaurantTable) -> Order | None:
    for order in reversed(table.orders):
        if order.status in ACTIVE_ORDER_STATUSES:
            return order
    return None


def get_latest_order_for_table(table: RestaurantTable) -> Order | None:
    if not table.orders:
        return None
    return list(sorted(table.orders, key=lambda order: order.id))[-1]


def get_pending_billing_orders_for_table(table: RestaurantTable) -> list[Order]:
    return [
        order
        for order in sorted(table.orders, key=lambda order: order.id, reverse=True)
        if order.status == OrderStatus.BILLING
    ]


def get_table_floor_status(table: RestaurantTable) -> TableStatus:
    if get_active_order_for_table(table):
        return TableStatus.RUNNING
    return TableStatus.EMPTY if table.status == TableStatus.EMPTY else TableStatus.RUNNING


def list_tables(db: Session) -> list[RestaurantTable]:
    return list(
        db.scalars(
            select(RestaurantTable)
            .order_by(RestaurantTable.id)
            .options(
                selectinload(RestaurantTable.orders)
                .selectinload(Order.items),
                selectinload(RestaurantTable.orders)
                .selectinload(Order.activities),
                selectinload(RestaurantTable.orders)
                .selectinload(Order.payments),
            )
        )
    )


def list_active_kitchen_tables(db: Session) -> list[RestaurantTable]:
    tables = list_tables(db)
    return [table for table in tables if get_active_order_for_table(table)]


def ensure_order_is_editable(order: Order) -> None:
    if order.status != OrderStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This order is no longer editable by the waiter",
        )


def ensure_order_is_not_closed(order: Order) -> None:
    if order.status == OrderStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This order is already closed",
        )


def ensure_item_belongs_to_order(order: Order, item_id: int) -> OrderItem:
    for item in order.items:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order item not found")


def add_activity(
    db: Session,
    *,
    order: Order,
    table: RestaurantTable,
    actor: User,
    action_type: ActivityAction,
    description: str,
    item: OrderItem | None = None,
    details: dict | None = None,
    quantity_before: int | None = None,
    quantity_after: int | None = None,
    note_before: str | None = None,
    note_after: str | None = None,
    item_name_before: str | None = None,
    item_name_after: str | None = None,
) -> OrderActivityLog:
    log = OrderActivityLog(
        order_id=order.id,
        table_id=table.id,
        item_id=item.id if item else None,
        actor_user_id=actor.id,
        actor_name=actor.display_name,
        actor_role=actor.role,
        action_type=action_type,
        description=description,
        details=details,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        note_before=note_before,
        note_after=note_after,
        item_name_before=item_name_before,
        item_name_after=item_name_after,
    )
    db.add(log)
    return log


def touch_order(order: Order) -> None:
    order.updated_at = utcnow()


def serialize_order_item(item: OrderItem) -> dict:
    return {
        "id": item.id,
        "item_name": item.item_name,
        "quantity": item.quantity,
        "note": item.note,
        "item_status": item.item_status,
        "kitchen_status": item.kitchen_status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "cancelled_at": item.cancelled_at,
    }


def serialize_activity(log: OrderActivityLog) -> dict:
    return {
        "id": log.id,
        "action_type": log.action_type,
        "actor_name": log.actor_name,
        "actor_role": log.actor_role,
        "description": log.description,
        "details": log.details,
        "quantity_before": log.quantity_before,
        "quantity_after": log.quantity_after,
        "note_before": log.note_before,
        "note_after": log.note_after,
        "item_name_before": log.item_name_before,
        "item_name_after": log.item_name_after,
        "created_at": log.created_at,
    }


def serialize_payment(payment: Payment) -> dict:
    return {
        "id": payment.id,
        "subtotal": float(payment.subtotal),
        "discount": float(payment.discount),
        "final_total": float(payment.final_total),
        "payment_method": payment.payment_method,
        "notes": payment.notes,
        "paid_at": payment.paid_at,
    }


def serialize_order(order: Order) -> dict:
    items = sorted(order.items, key=lambda item: item.id)
    activities = sorted(order.activities, key=lambda log: log.id, reverse=True)
    payments = sorted(order.payments, key=lambda payment: payment.id, reverse=True)
    return {
        "id": order.id,
        "table_id": order.table.id,
        "table_name": order.table.name,
        "status": order.status,
        "opened_at": order.opened_at,
        "updated_at": order.updated_at,
        "closed_at": order.closed_at,
        "items": [serialize_order_item(item) for item in items],
        "activity_log": [serialize_activity(log) for log in activities],
        "payments": [serialize_payment(payment) for payment in payments],
    }


def serialize_table(table: RestaurantTable) -> dict:
    active_order = get_active_order_for_table(table)
    pending_billing_orders = get_pending_billing_orders_for_table(table)
    latest_order = get_latest_order_for_table(table)
    floor_status = get_table_floor_status(table)
    active_items: list[OrderItem] = []
    ready_items: list[OrderItem] = []
    last_activity_at = table.updated_at
    if active_order:
        active_items = [item for item in active_order.items if item.item_status == OrderItemStatus.ACTIVE]
        ready_items = [
            item
            for item in active_items
            if item.kitchen_status == KitchenItemStatus.READY
        ]
        last_activity_at = active_order.updated_at
    elif pending_billing_orders:
        last_activity_at = pending_billing_orders[0].updated_at
    elif latest_order and latest_order.updated_at and latest_order.updated_at > last_activity_at:
        last_activity_at = latest_order.updated_at

    return {
        "id": table.id,
        "name": table.name,
        "status": floor_status,
        "active_order_id": active_order.id if active_order else None,
        "pending_bills_count": len(pending_billing_orders),
        "active_items_count": sum(item.quantity for item in active_items),
        "ready_items_count": sum(item.quantity for item in ready_items),
        "last_activity_at": last_activity_at,
        "current_order": serialize_order(active_order) if active_order else None,
    }


def open_table(db: Session, table: RestaurantTable, actor: User) -> Order:
    active_order = get_active_order_for_table(table)
    if active_order:
        return active_order

    if get_table_floor_status(table) != TableStatus.EMPTY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Waiter must mark this table empty before opening it again",
        )

    now = utcnow()
    order = Order(
        table_id=table.id,
        status=OrderStatus.RUNNING,
        opened_by_id=actor.id,
        opened_at=now,
        updated_at=now,
    )
    db.add(order)
    table.status = TableStatus.RUNNING
    db.flush()

    add_activity(
        db,
        order=order,
        table=table,
        actor=actor,
        action_type=ActivityAction.TABLE_OPENED,
        description=f"Opened {table.name} for service",
        details={"table_status": table.status.value},
    )
    db.flush()
    return order


def mark_table_empty(db: Session, table: RestaurantTable, actor: User) -> RestaurantTable:
    active_order = get_active_order_for_table(table)
    if active_order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This table still has an active order",
        )
    if get_table_floor_status(table) == TableStatus.EMPTY:
        return table

    latest_order = get_pending_billing_orders_for_table(table)[0] if get_pending_billing_orders_for_table(table) else get_latest_order_for_table(table)
    table.status = TableStatus.EMPTY
    table.updated_at = utcnow()
    db.flush()

    if latest_order:
        add_activity(
            db,
            order=latest_order,
            table=table,
            actor=actor,
            action_type=ActivityAction.TABLE_CLOSED,
            description=f"Waiter marked {table.name} empty for the next guests",
            details={"to": "empty"},
        )
        db.flush()
    return table


def add_item_to_order(
    db: Session,
    order: Order,
    item_name: str,
    quantity: int,
    note: str | None,
    actor: User,
) -> OrderItem:
    ensure_order_is_editable(order)
    now = utcnow()
    item = OrderItem(
        order_id=order.id,
        item_name=item_name.strip(),
        quantity=quantity,
        note=note.strip() if note else None,
        created_by_id=actor.id,
        updated_by_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    touch_order(order)
    db.flush()

    add_activity(
        db,
        order=order,
        table=order.table,
        actor=actor,
        action_type=ActivityAction.ITEM_ADDED,
        description=f"Added {quantity} x {item.item_name}",
        item=item,
        details={"quantity": quantity, "note": item.note},
        quantity_after=quantity,
        note_after=item.note,
        item_name_after=item.item_name,
    )
    db.flush()
    return item


def update_order_item(
    db: Session,
    order: Order,
    item: OrderItem,
    *,
    item_name: str,
    quantity: int,
    note: str | None,
    actor: User,
) -> OrderItem:
    ensure_order_is_editable(order)
    if item.item_status == OrderItemStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cancelled items cannot be edited",
        )

    previous_name = item.item_name
    previous_quantity = item.quantity
    previous_note = item.note

    item.item_name = item_name.strip()
    item.quantity = quantity
    item.note = note.strip() if note else None
    item.updated_by_id = actor.id
    item.updated_at = utcnow()
    touch_order(order)
    db.flush()

    add_activity(
        db,
        order=order,
        table=order.table,
        actor=actor,
        action_type=ActivityAction.ITEM_UPDATED,
        description=f"Updated {previous_name}",
        item=item,
        details={
            "from": {"name": previous_name, "quantity": previous_quantity, "note": previous_note},
            "to": {"name": item.item_name, "quantity": item.quantity, "note": item.note},
        },
        quantity_before=previous_quantity,
        quantity_after=item.quantity,
        note_before=previous_note,
        note_after=item.note,
        item_name_before=previous_name,
        item_name_after=item.item_name,
    )
    db.flush()
    return item


def cancel_order_item(db: Session, order: Order, item: OrderItem, actor: User) -> OrderItem:
    ensure_order_is_editable(order)
    if item.item_status == OrderItemStatus.CANCELLED:
        return item

    item.item_status = OrderItemStatus.CANCELLED
    item.cancelled_at = utcnow()
    item.updated_by_id = actor.id
    item.updated_at = utcnow()
    touch_order(order)
    db.flush()

    add_activity(
        db,
        order=order,
        table=order.table,
        actor=actor,
        action_type=ActivityAction.ITEM_CANCELLED,
        description=f"Cancelled {item.quantity} x {item.item_name}",
        item=item,
        details={"quantity": item.quantity, "note": item.note},
        quantity_before=item.quantity,
        quantity_after=item.quantity,
        note_before=item.note,
        note_after=item.note,
        item_name_before=item.item_name,
        item_name_after=item.item_name,
    )
    db.flush()
    return item


def update_kitchen_status(
    db: Session,
    order: Order,
    item: OrderItem,
    kitchen_status: KitchenItemStatus,
    actor: User,
) -> OrderItem:
    ensure_order_is_not_closed(order)
    if item.item_status == OrderItemStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cancelled items cannot be moved in the kitchen queue",
        )
    previous_status = item.kitchen_status
    item.kitchen_status = kitchen_status
    item.updated_at = utcnow()
    touch_order(order)
    db.flush()

    add_activity(
        db,
        order=order,
        table=order.table,
        actor=actor,
        action_type=ActivityAction.KITCHEN_STATUS_CHANGED,
        description=f"Kitchen marked {item.item_name} as {kitchen_status.value}",
        item=item,
        details={"from": previous_status.value, "to": kitchen_status.value},
        item_name_after=item.item_name,
    )
    db.flush()
    return item


def update_order_status(
    db: Session,
    order: Order,
    new_status: OrderStatus,
    actor: User,
) -> Order:
    ensure_order_is_not_closed(order)
    if new_status == OrderStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Closed status can only be set during checkout",
        )

    previous_status = order.status
    active_order = get_active_order_for_table(order.table)
    if (
        new_status == OrderStatus.RUNNING
        and active_order
        and active_order.id != order.id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This table already has a newer running order",
        )

    order.status = new_status
    if new_status == OrderStatus.RUNNING or order.table.status != TableStatus.EMPTY:
        order.table.status = TableStatus.RUNNING
    touch_order(order)
    db.flush()

    if previous_status != new_status:
        add_activity(
            db,
            order=order,
            table=order.table,
            actor=actor,
            action_type=ActivityAction.ORDER_STATUS_CHANGED,
            description=f"Moved order from {previous_status.value} to {new_status.value}",
            details={"from": previous_status.value, "to": new_status.value},
        )
        db.flush()
    return order


def find_order_item(db: Session, order: Order, item_id: int) -> OrderItem:
    item = ensure_item_belongs_to_order(order, item_id)
    db.refresh(item)
    return item


def count_existing_payments(order: Order) -> int:
    return len(order.payments)


def load_billing_items(order: Order) -> list[BillingItem]:
    return sorted(order.billing_items, key=lambda item: item.id)

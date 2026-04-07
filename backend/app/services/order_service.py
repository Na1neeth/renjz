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
from app.models.order_seat import OrderSeat
from app.models.payment import Payment
from app.models.table import RestaurantTable
from app.models.user import User


ACTIVE_ORDER_STATUSES = (OrderStatus.RUNNING,)
RESERVED_SEAT_ORDER_STATUSES = (OrderStatus.RUNNING, OrderStatus.BILLING, OrderStatus.CLOSED)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_table(db: Session, table_id: int) -> RestaurantTable:
    table = db.scalar(
        select(RestaurantTable)
        .where(RestaurantTable.id == table_id)
        .options(
            selectinload(RestaurantTable.orders).selectinload(Order.items),
            selectinload(RestaurantTable.orders).selectinload(Order.activities),
            selectinload(RestaurantTable.orders).selectinload(Order.payments),
            selectinload(RestaurantTable.orders).selectinload(Order.billing_items),
            selectinload(RestaurantTable.orders).selectinload(Order.seats),
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
            selectinload(Order.seats),
        )
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def get_orders_for_current_cycle(table: RestaurantTable) -> list[Order]:
    return [
        order
        for order in sorted(table.orders, key=lambda row: row.id)
        if order.service_cycle == table.service_cycle
    ]


def get_active_orders_for_table(table: RestaurantTable) -> list[Order]:
    return [
        order
        for order in get_orders_for_current_cycle(table)
        if order.status in ACTIVE_ORDER_STATUSES
    ]


def get_active_order_for_table(table: RestaurantTable) -> Order | None:
    active_orders = get_active_orders_for_table(table)
    return active_orders[-1] if active_orders else None


def get_latest_order_for_table(table: RestaurantTable) -> Order | None:
    if not table.orders:
        return None
    return sorted(table.orders, key=lambda order: order.id)[-1]


def get_pending_billing_orders_for_table(table: RestaurantTable) -> list[Order]:
    return [
        order
        for order in sorted(table.orders, key=lambda order: order.updated_at or order.id, reverse=True)
        if order.status == OrderStatus.BILLING
    ]


def sort_orders_oldest_first(orders: list[Order]) -> list[Order]:
    return sorted(
        orders,
        key=lambda order: (order.updated_at or order.opened_at, order.id),
    )


def sort_items_oldest_first(items: list[OrderItem]) -> list[OrderItem]:
    return sorted(
        items,
        key=lambda item: (item.updated_at or item.created_at, item.id),
    )


def get_reserved_orders_for_table(table: RestaurantTable) -> list[Order]:
    if table.status == TableStatus.EMPTY:
        return []
    return [
        order
        for order in get_orders_for_current_cycle(table)
        if order.status in RESERVED_SEAT_ORDER_STATUSES
    ]


def get_order_seat_numbers(order: Order) -> list[int]:
    return sorted({seat.seat_number for seat in order.seats})


def format_seat_label(seat_numbers: list[int]) -> str:
    if not seat_numbers:
        return "No seats"
    if len(seat_numbers) == 1:
        return f"Seat {seat_numbers[0]}"
    return f"Seats {' + '.join(str(number) for number in seat_numbers)}"


def get_reserved_seat_map(table: RestaurantTable) -> dict[int, Order]:
    seat_map: dict[int, Order] = {}
    for order in sorted(
        get_reserved_orders_for_table(table),
        key=lambda row: (row.status != OrderStatus.RUNNING, row.id),
    ):
        for seat_number in get_order_seat_numbers(order):
            seat_map.setdefault(seat_number, order)
    return seat_map


def get_table_floor_status(table: RestaurantTable) -> TableStatus:
    return TableStatus.EMPTY if table.status == TableStatus.EMPTY else TableStatus.RUNNING


def list_tables(db: Session) -> list[RestaurantTable]:
    return list(
        db.scalars(
            select(RestaurantTable)
            .order_by(RestaurantTable.id)
            .options(
                selectinload(RestaurantTable.orders).selectinload(Order.items),
                selectinload(RestaurantTable.orders).selectinload(Order.activities),
                selectinload(RestaurantTable.orders).selectinload(Order.payments),
                selectinload(RestaurantTable.orders).selectinload(Order.billing_items),
                selectinload(RestaurantTable.orders).selectinload(Order.seats),
            )
        )
    )


def list_active_kitchen_tables(db: Session) -> list[RestaurantTable]:
    tables = list_tables(db)
    active_tables = [table for table in tables if get_active_orders_for_table(table)]
    return sorted(
        active_tables,
        key=lambda table: (
            max(
                (order.updated_at or order.opened_at for order in get_active_orders_for_table(table)),
                default=table.updated_at,
            ),
            table.id,
        ),
    )


def ensure_order_is_editable(order: Order) -> None:
    if order.status != OrderStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This check is no longer editable by the waiter",
        )


def ensure_order_is_not_closed(order: Order) -> None:
    if order.status == OrderStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This check is already closed",
        )


def ensure_item_belongs_to_order(order: Order, item_id: int) -> OrderItem:
    for item in order.items:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order item not found")


def validate_seat_numbers(table: RestaurantTable, seat_numbers: list[int]) -> list[int]:
    normalized = sorted({int(number) for number in seat_numbers})
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one seat for this check",
        )

    invalid = [number for number in normalized if number < 1 or number > table.seat_count]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Seat numbers must be between 1 and {table.seat_count}",
        )
    return normalized


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


def serialize_order(order: Order, *, kitchen_view: bool = False) -> dict:
    items = sort_items_oldest_first(order.items) if kitchen_view else sorted(order.items, key=lambda item: item.id)
    activities = sorted(order.activities, key=lambda log: log.id, reverse=True)
    payments = sorted(order.payments, key=lambda payment: payment.id, reverse=True)
    seat_numbers = get_order_seat_numbers(order)
    return {
        "id": order.id,
        "table_id": order.table.id,
        "table_name": order.table.name,
        "service_cycle": order.service_cycle,
        "seat_numbers": seat_numbers,
        "seat_label": format_seat_label(seat_numbers),
        "status": order.status,
        "opened_at": order.opened_at,
        "updated_at": order.updated_at,
        "closed_at": order.closed_at,
        "items": [serialize_order_item(item) for item in items],
        "activity_log": [serialize_activity(log) for log in activities],
        "payments": [serialize_payment(payment) for payment in payments],
    }


def serialize_table(table: RestaurantTable, *, kitchen_view: bool = False) -> dict:
    active_orders = get_active_orders_for_table(table)
    ordered_active_orders = sort_orders_oldest_first(active_orders) if kitchen_view else active_orders
    active_order = ordered_active_orders[-1] if ordered_active_orders else None
    pending_billing_orders = get_pending_billing_orders_for_table(table)
    latest_order = get_latest_order_for_table(table)
    floor_status = get_table_floor_status(table)
    reserved_seat_map = get_reserved_seat_map(table)

    active_items = [
        item
        for order in active_orders
        for item in order.items
        if item.item_status == OrderItemStatus.ACTIVE
    ]
    ready_items = [
        item
        for item in active_items
        if item.kitchen_status == KitchenItemStatus.READY
    ]

    last_activity_at = table.updated_at
    if active_orders:
        last_activity_at = max(order.updated_at for order in active_orders if order.updated_at)
    elif pending_billing_orders:
        last_activity_at = pending_billing_orders[0].updated_at
    elif latest_order and latest_order.updated_at and latest_order.updated_at > last_activity_at:
        last_activity_at = latest_order.updated_at

    seats = []
    for seat_number in range(1, table.seat_count + 1):
        order = reserved_seat_map.get(seat_number)
        seat_numbers = get_order_seat_numbers(order) if order else []
        seats.append(
            {
                "seat_number": seat_number,
                "status": "occupied" if order else "available",
                "order_id": order.id if order else None,
                "seat_label": format_seat_label(seat_numbers) if order else None,
            }
        )

    return {
        "id": table.id,
        "name": table.name,
        "seat_count": table.seat_count,
        "service_cycle": table.service_cycle,
        "status": floor_status,
        "active_order_id": active_order.id if active_order else None,
        "active_orders_count": len(active_orders),
        "pending_bills_count": len(pending_billing_orders),
        "active_items_count": sum(item.quantity for item in active_items),
        "ready_items_count": sum(item.quantity for item in ready_items),
        "last_activity_at": last_activity_at,
        "current_order": serialize_order(active_order, kitchen_view=kitchen_view) if active_order else None,
        "active_orders": [serialize_order(order, kitchen_view=kitchen_view) for order in ordered_active_orders],
        "seats": seats,
    }


def open_table(db: Session, table: RestaurantTable, actor: User) -> RestaurantTable:
    del actor
    if table.status == TableStatus.EMPTY:
        table.status = TableStatus.RUNNING
        table.service_cycle += 1
        table.updated_at = utcnow()
        db.flush()
    return table


def create_check_for_table(
    db: Session,
    table: RestaurantTable,
    seat_numbers: list[int],
    actor: User,
) -> Order:
    if table.status == TableStatus.EMPTY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Open the table before starting a seat check",
        )

    normalized_seats = validate_seat_numbers(table, seat_numbers)
    reserved_seat_map = get_reserved_seat_map(table)
    conflicting = [number for number in normalized_seats if number in reserved_seat_map]
    if conflicting:
        conflict_order = reserved_seat_map[conflicting[0]]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{format_seat_label(conflicting)} is already part of {format_seat_label(get_order_seat_numbers(conflict_order))}",
        )

    now = utcnow()
    order = Order(
        table_id=table.id,
        service_cycle=table.service_cycle,
        status=OrderStatus.RUNNING,
        opened_by_id=actor.id,
        opened_at=now,
        updated_at=now,
    )
    db.add(order)
    db.flush()

    db.add_all(
        [OrderSeat(order_id=order.id, seat_number=seat_number) for seat_number in normalized_seats]
    )
    table.updated_at = now
    db.flush()

    add_activity(
        db,
        order=order,
        table=table,
        actor=actor,
        action_type=ActivityAction.TABLE_OPENED,
        description=f"Started {format_seat_label(normalized_seats)} on {table.name}",
        details={"seat_numbers": normalized_seats, "service_cycle": table.service_cycle},
    )
    db.flush()
    return order


def mark_table_empty(db: Session, table: RestaurantTable, actor: User) -> RestaurantTable:
    active_orders = get_active_orders_for_table(table)
    if active_orders:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This table still has active seat checks",
        )
    if table.status == TableStatus.EMPTY:
        return table

    current_cycle_orders = get_orders_for_current_cycle(table)
    latest_order = current_cycle_orders[-1] if current_cycle_orders else None
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
            details={"to": "empty", "service_cycle": table.service_cycle},
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
        description=f"Added {quantity} x {item.item_name} to {format_seat_label(get_order_seat_numbers(order))}",
        item=item,
        details={"quantity": quantity, "note": item.note, "seat_numbers": get_order_seat_numbers(order)},
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
        description=f"Updated {previous_name} on {format_seat_label(get_order_seat_numbers(order))}",
        item=item,
        details={
            "from": {"name": previous_name, "quantity": previous_quantity, "note": previous_note},
            "to": {"name": item.item_name, "quantity": item.quantity, "note": item.note},
            "seat_numbers": get_order_seat_numbers(order),
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
        description=f"Cancelled {item.quantity} x {item.item_name} on {format_seat_label(get_order_seat_numbers(order))}",
        item=item,
        details={"quantity": item.quantity, "note": item.note, "seat_numbers": get_order_seat_numbers(order)},
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
        description=f"Kitchen marked {item.item_name} for {format_seat_label(get_order_seat_numbers(order))} as {kitchen_status.value}",
        item=item,
        details={
            "from": previous_status.value,
            "to": kitchen_status.value,
            "seat_numbers": get_order_seat_numbers(order),
        },
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
    seat_numbers = get_order_seat_numbers(order)
    if new_status == OrderStatus.RUNNING:
        if order.table.status == TableStatus.EMPTY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This table was already cleared for the next guests",
            )
        if order.service_cycle != order.table.service_cycle:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This bill belongs to an older table session",
            )
        active_orders = [row for row in get_active_orders_for_table(order.table) if row.id != order.id]
        for active_order in active_orders:
            if set(seat_numbers) & set(get_order_seat_numbers(active_order)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Those seats already have a newer running check",
                )

    order.status = new_status
    if order.table.status != TableStatus.EMPTY:
        order.table.status = TableStatus.RUNNING
    order.table.updated_at = utcnow()
    touch_order(order)
    db.flush()

    if previous_status != new_status:
        add_activity(
            db,
            order=order,
            table=order.table,
            actor=actor,
            action_type=ActivityAction.ORDER_STATUS_CHANGED,
            description=f"Moved {format_seat_label(seat_numbers)} from {previous_status.value} to {new_status.value}",
            details={
                "from": previous_status.value,
                "to": new_status.value,
                "seat_numbers": seat_numbers,
            },
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

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, text

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.billing_item import BillingItem
from app.models.enums import (
    ActivityAction,
    KitchenItemStatus,
    OrderItemStatus,
    OrderStatus,
    TableStatus,
    UserRole,
)
from app.models.order import Order
from app.models.order_activity_log import OrderActivityLog
from app.models.order_item import OrderItem
from app.models.table import RestaurantTable
from app.models.user import User


TABLE_LABELS = [
    "A1",
    "A2",
    "A3",
    "A4",
    "B1",
    "B2",
    "B3",
    "B4",
    "B5",
    "C1",
    "C2",
    "C3",
    "C4",
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    sync_postgres_enums()
    seed_data()


def sync_postgres_enums() -> None:
    if engine.dialect.name != "postgresql":
        return

    enum_values = {
        "userrole": [role.value for role in UserRole],
        "tablestatus": [status.value for status in TableStatus],
        "orderstatus": [status.value for status in OrderStatus],
        "orderitemstatus": [status.value for status in OrderItemStatus],
        "kitchenitemstatus": [status.value for status in KitchenItemStatus],
        "activityaction": [action.value for action in ActivityAction],
    }

    with engine.begin() as connection:
        for type_name, values in enum_values.items():
            exists = connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :type_name)"),
                {"type_name": type_name},
            ).scalar()
            if not exists:
                continue

            for value in values:
                safe_value = value.replace("'", "''")
                connection.execute(
                    text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{safe_value}'")
                )


def seed_data() -> None:
    db = SessionLocal()
    try:
        waiter = db.scalar(select(User).where(User.username == "waiter"))
        if not waiter:
            waiter = User(
                username="waiter",
                display_name="Demo Waiter",
                password_hash=get_password_hash("demo123"),
                role=UserRole.WAITER,
            )
            db.add(waiter)

        kitchen = db.scalar(select(User).where(User.username == "kitchen"))
        if not kitchen:
            kitchen = User(
                username="kitchen",
                display_name="Demo Kitchen",
                password_hash=get_password_hash("demo123"),
                role=UserRole.KITCHEN,
            )
            db.add(kitchen)

        receptionist = db.scalar(select(User).where(User.username == "reception"))
        if not receptionist:
            receptionist = User(
                username="reception",
                display_name="Demo Reception",
                password_hash=get_password_hash("demo123"),
                role=UserRole.RECEPTIONIST,
            )
            db.add(receptionist)

        db.flush()

        existing_tables = {
            table.name: table for table in db.scalars(select(RestaurantTable).order_by(RestaurantTable.id))
        }
        for index, label in enumerate(TABLE_LABELS, start=1):
            legacy_name = f"Table {index}"
            if label in existing_tables:
                continue
            if legacy_name in existing_tables:
                existing_tables[legacy_name].name = label
                continue

            status = TableStatus.EMPTY
            db.add(RestaurantTable(name=label, status=status))
        db.flush()

        tables = list(db.scalars(select(RestaurantTable).order_by(RestaurantTable.id)))
        if db.scalar(select(Order.id).limit(1)):
            db.commit()
            return

        now = datetime.now(timezone.utc)

        running_order = Order(
            table_id=tables[1].id,
            status=OrderStatus.RUNNING,
            opened_by_id=waiter.id,
            opened_at=now,
            updated_at=now,
        )
        billing_order = Order(
            table_id=tables[4].id,
            status=OrderStatus.BILLING,
            opened_by_id=waiter.id,
            opened_at=now,
            updated_at=now,
        )
        tables[1].status = TableStatus.RUNNING
        tables[4].status = TableStatus.RUNNING
        db.add_all([running_order, billing_order])
        db.flush()

        running_items = [
            OrderItem(
                order_id=running_order.id,
                item_name="Butter naan",
                quantity=2,
                note="",
                kitchen_status=KitchenItemStatus.NEW,
                item_status=OrderItemStatus.ACTIVE,
                created_by_id=waiter.id,
                updated_by_id=waiter.id,
                created_at=now,
                updated_at=now,
            ),
            OrderItem(
                order_id=running_order.id,
                item_name="Paneer curry",
                quantity=1,
                note="less spicy",
                kitchen_status=KitchenItemStatus.NEW,
                item_status=OrderItemStatus.ACTIVE,
                created_by_id=waiter.id,
                updated_by_id=waiter.id,
                created_at=now,
                updated_at=now,
            ),
            OrderItem(
                order_id=running_order.id,
                item_name="Lime soda",
                quantity=1,
                note="no ice",
                kitchen_status=KitchenItemStatus.NEW,
                item_status=OrderItemStatus.CANCELLED,
                created_by_id=waiter.id,
                updated_by_id=waiter.id,
                cancelled_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
        billing_items = [
            OrderItem(
                order_id=billing_order.id,
                item_name="Masala dosa",
                quantity=3,
                note="",
                kitchen_status=KitchenItemStatus.READY,
                item_status=OrderItemStatus.ACTIVE,
                created_by_id=waiter.id,
                updated_by_id=waiter.id,
                created_at=now,
                updated_at=now,
            ),
            OrderItem(
                order_id=billing_order.id,
                item_name="Filter coffee",
                quantity=1,
                note="",
                kitchen_status=KitchenItemStatus.READY,
                item_status=OrderItemStatus.ACTIVE,
                created_by_id=waiter.id,
                updated_by_id=waiter.id,
                created_at=now,
                updated_at=now,
            ),
            OrderItem(
                order_id=billing_order.id,
                item_name="Extra chutney",
                quantity=1,
                note="complimentary request",
                kitchen_status=KitchenItemStatus.READY,
                item_status=OrderItemStatus.CANCELLED,
                created_by_id=waiter.id,
                updated_by_id=waiter.id,
                cancelled_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
        db.add_all(running_items + billing_items)
        db.flush()

        db.add_all(
            [
                BillingItem(
                    order_id=billing_order.id,
                    order_item_id=billing_items[0].id,
                    item_name="Masala dosa",
                    note="",
                    source_status=OrderItemStatus.ACTIVE.value,
                    consumed_quantity=3,
                    billed_quantity=3,
                    unit_price=Decimal("120.00"),
                    include_in_bill=True,
                ),
                BillingItem(
                    order_id=billing_order.id,
                    order_item_id=billing_items[1].id,
                    item_name="Filter coffee",
                    note="",
                    source_status=OrderItemStatus.ACTIVE.value,
                    consumed_quantity=1,
                    billed_quantity=1,
                    unit_price=Decimal("60.00"),
                    include_in_bill=True,
                ),
                BillingItem(
                    order_id=billing_order.id,
                    order_item_id=billing_items[2].id,
                    item_name="Extra chutney",
                    note="complimentary request",
                    source_status=OrderItemStatus.CANCELLED.value,
                    consumed_quantity=1,
                    billed_quantity=0,
                    unit_price=Decimal("0.00"),
                    include_in_bill=False,
                ),
            ]
        )

        db.add_all(
            [
                OrderActivityLog(
                    order_id=running_order.id,
                    table_id=tables[1].id,
                    actor_user_id=waiter.id,
                    actor_name=waiter.display_name,
                    actor_role=waiter.role,
                    action_type=ActivityAction.TABLE_OPENED,
                    description="Opened A2 for service",
                    details={},
                ),
                OrderActivityLog(
                    order_id=running_order.id,
                    table_id=tables[1].id,
                    item_id=running_items[0].id,
                    actor_user_id=waiter.id,
                    actor_name=waiter.display_name,
                    actor_role=waiter.role,
                    action_type=ActivityAction.ITEM_ADDED,
                    description="Added 2 x Butter naan",
                    item_name_after="Butter naan",
                    quantity_after=2,
                    note_after="",
                    details={"quantity": 2},
                ),
                OrderActivityLog(
                    order_id=running_order.id,
                    table_id=tables[1].id,
                    item_id=running_items[1].id,
                    actor_user_id=waiter.id,
                    actor_name=waiter.display_name,
                    actor_role=waiter.role,
                    action_type=ActivityAction.ITEM_ADDED,
                    description="Added 1 x Paneer curry",
                    item_name_after="Paneer curry",
                    quantity_after=1,
                    note_after="less spicy",
                    details={"quantity": 1, "note": "less spicy"},
                ),
                OrderActivityLog(
                    order_id=running_order.id,
                    table_id=tables[1].id,
                    item_id=running_items[2].id,
                    actor_user_id=waiter.id,
                    actor_name=waiter.display_name,
                    actor_role=waiter.role,
                    action_type=ActivityAction.ITEM_CANCELLED,
                    description="Cancelled 1 x Lime soda",
                    item_name_after="Lime soda",
                    quantity_after=1,
                    note_after="no ice",
                    details={"quantity": 1, "note": "no ice"},
                ),
                OrderActivityLog(
                    order_id=billing_order.id,
                    table_id=tables[4].id,
                    actor_user_id=waiter.id,
                    actor_name=waiter.display_name,
                    actor_role=waiter.role,
                    action_type=ActivityAction.TABLE_OPENED,
                    description="Opened B1 for service",
                    details={},
                ),
                OrderActivityLog(
                    order_id=billing_order.id,
                    table_id=tables[4].id,
                    actor_user_id=receptionist.id,
                    actor_name=receptionist.display_name,
                    actor_role=receptionist.role,
                    action_type=ActivityAction.ORDER_STATUS_CHANGED,
                    description="Moved order from running to billing",
                    details={"from": "running", "to": "billing"},
                ),
            ]
        )

        db.commit()
    finally:
        db.close()

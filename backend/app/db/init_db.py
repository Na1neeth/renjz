from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.billing_item import BillingItem
from app.models.menu_item import MenuItem
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
from app.models.order_seat import OrderSeat
from app.models.table import RestaurantTable
from app.models.user import User
from app.services.menu_service import normalize_menu_item_name


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

STAFF_USERS = [
    {
        "username": "reception1",
        "display_name": "Reception 1",
        "password": "3001",
        "role": UserRole.RECEPTIONIST,
    },
    {
        "username": "kitchen1",
        "display_name": "Kitchen 1",
        "password": "2001",
        "role": UserRole.KITCHEN,
    },
    {
        "username": "sales1",
        "display_name": "Sales 1",
        "password": "4001",
        "role": UserRole.SALES,
    },
    {
        "username": "waiter1",
        "display_name": "Waiter 1",
        "password": "1001",
        "role": UserRole.WAITER,
    },
    {
        "username": "waiter2",
        "display_name": "Waiter 2",
        "password": "1002",
        "role": UserRole.WAITER,
    },
    {
        "username": "waiter3",
        "display_name": "Waiter 3",
        "password": "1003",
        "role": UserRole.WAITER,
    },
    {
        "username": "waiter4",
        "display_name": "Waiter 4",
        "password": "1004",
        "role": UserRole.WAITER,
    },
    {
        "username": "waiter5",
        "display_name": "Waiter 5",
        "password": "1005",
        "role": UserRole.WAITER,
    },
]

DEFAULT_MENU_ITEMS = [
    "Butter naan",
    "Paneer curry",
    "Lime soda",
    "Tomato soup",
    "Masala dosa",
    "Filter coffee",
]


def seat_count_for_table_name(table_name: str) -> int:
    normalized = str(table_name or "").strip().upper()
    if normalized.startswith("B") and normalized != "B5":
        return 2
    return 4


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    sync_postgres_enums()
    sync_additive_schema()
    migrate_legacy_enum_rows()
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


def sync_additive_schema() -> None:
    additive_columns = {
        "tables": {
            "seat_count": "INTEGER",
            "service_cycle": "INTEGER",
        },
        "orders": {
            "service_cycle": "INTEGER",
        },
        "users": {
            "active_session_key": "VARCHAR(64)",
            "active_session_expires_at": "TIMESTAMP WITH TIME ZONE",
        },
    }

    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additive_columns.items():
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                )


def migrate_legacy_enum_rows() -> None:
    if engine.dialect.name != "postgresql":
        return

    enum_updates = [
        ("users", "role", "userrole", UserRole),
        ("tables", "status", "tablestatus", TableStatus),
        ("orders", "status", "orderstatus", OrderStatus),
        ("order_items", "item_status", "orderitemstatus", OrderItemStatus),
        ("order_items", "kitchen_status", "kitchenitemstatus", KitchenItemStatus),
        ("order_activity_logs", "actor_role", "userrole", UserRole),
        ("order_activity_logs", "action_type", "activityaction", ActivityAction),
    ]

    with engine.begin() as connection:
        for table_name, column_name, enum_type_name, enum_cls in enum_updates:
            for member in enum_cls:
                legacy_value = member.name
                current_value = member.value
                if legacy_value == current_value:
                    continue
                connection.execute(
                    text(
                        f"""
                        UPDATE {table_name}
                        SET {column_name} = CAST(:current_value AS {enum_type_name})
                        WHERE {column_name}::text = :legacy_value
                        """
                    ),
                    {"current_value": current_value, "legacy_value": legacy_value},
                )


def backfill_seat_runtime_data(db) -> None:
    tables = list(
        db.scalars(
            select(RestaurantTable)
            .order_by(RestaurantTable.id)
            .options(selectinload(RestaurantTable.orders).selectinload(Order.seats))
        )
    )

    for table in tables:
        table.seat_count = seat_count_for_table_name(table.name)
        if not table.service_cycle:
            table.service_cycle = 1 if table.orders or table.status != TableStatus.EMPTY else 0

    db.flush()

    for table in tables:
        for order in table.orders:
            if not order.service_cycle:
                order.service_cycle = table.service_cycle or 1
            if order.seats:
                continue
            db.add_all(
                [
                    OrderSeat(order_id=order.id, seat_number=seat_number)
                    for seat_number in range(1, table.seat_count + 1)
                ]
            )

    db.flush()


def seed_data() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        user_lookup = {
            user.username: user
            for user in db.scalars(select(User).order_by(User.id))
        }

        for staff in STAFF_USERS:
            user = user_lookup.get(staff["username"])
            if not user:
                user = User(
                    username=staff["username"],
                    display_name=staff["display_name"],
                    password_hash=get_password_hash(staff["password"]),
                    role=staff["role"],
                    is_active=True,
                )
                db.add(user)
                user_lookup[staff["username"]] = user
                continue

            user.display_name = staff["display_name"]
            user.password_hash = get_password_hash(staff["password"])
            user.role = staff["role"]
            user.is_active = True

        for legacy_username in ("waiter", "kitchen", "reception"):
            legacy_user = user_lookup.get(legacy_username)
            if legacy_user:
                legacy_user.is_active = False
                legacy_user.active_session_key = None
                legacy_user.active_session_expires_at = None

        db.flush()

        waiter = user_lookup["waiter1"]
        receptionist = user_lookup["reception1"]

        existing_tables = {
            table.name: table for table in db.scalars(select(RestaurantTable).order_by(RestaurantTable.id))
        }
        for index, label in enumerate(TABLE_LABELS, start=1):
            legacy_name = f"Table {index}"
            if label in existing_tables:
                existing_tables[label].seat_count = seat_count_for_table_name(label)
                continue
            if legacy_name in existing_tables:
                existing_tables[legacy_name].name = label
                existing_tables[legacy_name].seat_count = seat_count_for_table_name(label)
                continue

            status = TableStatus.EMPTY
            db.add(
                RestaurantTable(
                    name=label,
                    status=status,
                    seat_count=seat_count_for_table_name(label),
                    service_cycle=0,
                )
            )
        db.flush()

        backfill_seat_runtime_data(db)
        seed_menu_items(db)

        tables = list(db.scalars(select(RestaurantTable).order_by(RestaurantTable.id)))
        if db.scalar(select(Order.id).limit(1)):
            db.commit()
            return

        if not settings.seed_demo_data:
            db.commit()
            return

        now = datetime.now(timezone.utc)

        running_order = Order(
            table_id=tables[1].id,
            service_cycle=1,
            status=OrderStatus.RUNNING,
            opened_by_id=waiter.id,
            opened_at=now,
            updated_at=now,
        )
        split_order = Order(
            table_id=tables[1].id,
            service_cycle=1,
            status=OrderStatus.RUNNING,
            opened_by_id=waiter.id,
            opened_at=now,
            updated_at=now,
        )
        billing_order = Order(
            table_id=tables[4].id,
            service_cycle=1,
            status=OrderStatus.BILLING,
            opened_by_id=waiter.id,
            opened_at=now,
            updated_at=now,
        )
        tables[1].status = TableStatus.RUNNING
        tables[1].service_cycle = 1
        tables[4].status = TableStatus.RUNNING
        tables[4].service_cycle = 1
        db.add_all([running_order, split_order, billing_order])
        db.flush()

        db.add_all(
            [
                OrderSeat(order_id=running_order.id, seat_number=1),
                OrderSeat(order_id=running_order.id, seat_number=2),
                OrderSeat(order_id=split_order.id, seat_number=3),
                OrderSeat(order_id=billing_order.id, seat_number=1),
                OrderSeat(order_id=billing_order.id, seat_number=2),
            ]
        )

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
        split_items = [
            OrderItem(
                order_id=split_order.id,
                item_name="Tomato soup",
                quantity=1,
                note="less salt",
                kitchen_status=KitchenItemStatus.NEW,
                item_status=OrderItemStatus.ACTIVE,
                created_by_id=waiter.id,
                updated_by_id=waiter.id,
                created_at=now,
                updated_at=now,
            )
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
        db.add_all(running_items + split_items + billing_items)
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
                    description="Started Seats 1 + 2 on A2",
                    details={"seat_numbers": [1, 2], "service_cycle": 1},
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
                    details={"quantity": 1, "note": "less spicy", "seat_numbers": [1, 2]},
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
                    details={"quantity": 1, "note": "no ice", "seat_numbers": [1, 2]},
                ),
                OrderActivityLog(
                    order_id=split_order.id,
                    table_id=tables[1].id,
                    actor_user_id=waiter.id,
                    actor_name=waiter.display_name,
                    actor_role=waiter.role,
                    action_type=ActivityAction.TABLE_OPENED,
                    description="Started Seat 3 on A2",
                    details={"seat_numbers": [3], "service_cycle": 1},
                ),
                OrderActivityLog(
                    order_id=split_order.id,
                    table_id=tables[1].id,
                    item_id=split_items[0].id,
                    actor_user_id=waiter.id,
                    actor_name=waiter.display_name,
                    actor_role=waiter.role,
                    action_type=ActivityAction.ITEM_ADDED,
                    description="Added 1 x Tomato soup",
                    item_name_after="Tomato soup",
                    quantity_after=1,
                    note_after="less salt",
                    details={"quantity": 1, "note": "less salt", "seat_numbers": [3]},
                ),
                OrderActivityLog(
                    order_id=billing_order.id,
                    table_id=tables[4].id,
                    actor_user_id=waiter.id,
                    actor_name=waiter.display_name,
                    actor_role=waiter.role,
                    action_type=ActivityAction.TABLE_OPENED,
                    description="Started Seats 1 + 2 on B1",
                    details={"seat_numbers": [1, 2], "service_cycle": 1},
                ),
                OrderActivityLog(
                    order_id=billing_order.id,
                    table_id=tables[4].id,
                    actor_user_id=receptionist.id,
                    actor_name=receptionist.display_name,
                    actor_role=receptionist.role,
                    action_type=ActivityAction.ORDER_STATUS_CHANGED,
                    description="Moved Seats 1 + 2 from running to billing",
                    details={"from": "running", "to": "billing", "seat_numbers": [1, 2]},
                ),
            ]
        )

        db.commit()
    finally:
        db.close()


def seed_menu_items(db) -> None:
    if db.scalar(select(MenuItem.id).limit(1)):
        return

    names = []
    seen = set()

    historical_names = db.scalars(select(OrderItem.item_name).distinct().order_by(OrderItem.item_name))
    for raw_name in historical_names:
        normalized_name = normalize_menu_item_name(raw_name)
        if not normalized_name or normalized_name.lower() in seen:
            continue
        names.append(normalized_name)
        seen.add(normalized_name.lower())

    if not names:
        for raw_name in DEFAULT_MENU_ITEMS:
            normalized_name = normalize_menu_item_name(raw_name)
            if normalized_name.lower() in seen:
                continue
            names.append(normalized_name)
            seen.add(normalized_name.lower())

    db.add_all([MenuItem(name=name) for name in names])
    db.flush()

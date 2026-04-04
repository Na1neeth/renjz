from enum import Enum


class UserRole(str, Enum):
    WAITER = "waiter"
    KITCHEN = "kitchen"
    RECEPTIONIST = "receptionist"


class TableStatus(str, Enum):
    EMPTY = "empty"
    RUNNING = "running"
    BILLING = "billing"
    CLOSED = "closed"


class OrderStatus(str, Enum):
    RUNNING = "running"
    BILLING = "billing"
    CLOSED = "closed"


class OrderItemStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class KitchenItemStatus(str, Enum):
    NEW = "new"
    PREPARING = "preparing"
    READY = "ready"


class ActivityAction(str, Enum):
    TABLE_OPENED = "table_opened"
    TABLE_MARKED_EMPTY = "table_marked_empty"
    ITEM_ADDED = "item_added"
    ITEM_UPDATED = "item_updated"
    ITEM_CANCELLED = "item_cancelled"
    KITCHEN_STATUS_CHANGED = "kitchen_status_changed"
    ORDER_STATUS_CHANGED = "order_status_changed"
    BILLING_SAVED = "billing_saved"
    PAYMENT_COMPLETED = "payment_completed"
    TABLE_CLOSED = "table_closed"

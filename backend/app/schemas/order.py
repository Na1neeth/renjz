from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    ActivityAction,
    KitchenItemStatus,
    OrderItemStatus,
    OrderStatus,
    UserRole,
)


class OrderItemCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    quantity: int = Field(ge=1, le=99)
    note: str | None = Field(default=None, max_length=1000)


class OrderItemUpdate(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    quantity: int = Field(ge=1, le=99)
    note: str | None = Field(default=None, max_length=1000)


class KitchenStatusUpdateRequest(BaseModel):
    kitchen_status: KitchenItemStatus


class OrderStatusUpdateRequest(BaseModel):
    status: OrderStatus


class OrderItemRead(BaseModel):
    id: int
    item_name: str
    quantity: int
    note: str | None
    item_status: OrderItemStatus
    kitchen_status: KitchenItemStatus
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None


class OrderActivityRead(BaseModel):
    id: int
    action_type: ActivityAction
    actor_name: str
    actor_role: UserRole
    description: str
    details: dict | None
    quantity_before: int | None
    quantity_after: int | None
    note_before: str | None
    note_after: str | None
    item_name_before: str | None
    item_name_after: str | None
    created_at: datetime


class PaymentRead(BaseModel):
    id: int
    subtotal: float
    discount: float
    final_total: float
    payment_method: str
    notes: str | None
    paid_at: datetime


class OrderRead(BaseModel):
    id: int
    table_id: int
    table_name: str
    service_cycle: int
    seat_numbers: list[int]
    seat_label: str
    status: OrderStatus
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    items: list[OrderItemRead]
    activity_log: list[OrderActivityRead]
    payments: list[PaymentRead]

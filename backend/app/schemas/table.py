from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import TableStatus
from app.schemas.order import OrderRead


class TableSeatRead(BaseModel):
    seat_number: int
    status: str
    order_id: int | None
    seat_label: str | None


class TableCheckCreate(BaseModel):
    seat_numbers: list[int] = Field(min_length=1)


class TableSummary(BaseModel):
    id: int
    name: str
    seat_count: int
    service_cycle: int
    status: TableStatus
    active_order_id: int | None
    active_orders_count: int
    pending_bills_count: int
    active_items_count: int
    ready_items_count: int
    last_activity_at: datetime | None


class TableDetail(TableSummary):
    current_order: OrderRead | None
    active_orders: list[OrderRead]
    seats: list[TableSeatRead]

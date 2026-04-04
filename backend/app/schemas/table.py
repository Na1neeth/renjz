from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TableStatus
from app.schemas.order import OrderRead


class TableSummary(BaseModel):
    id: int
    name: str
    status: TableStatus
    active_order_id: int | None
    pending_bills_count: int
    active_items_count: int
    ready_items_count: int
    last_activity_at: datetime | None


class TableDetail(TableSummary):
    current_order: OrderRead | None

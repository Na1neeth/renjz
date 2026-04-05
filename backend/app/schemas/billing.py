from datetime import datetime

from pydantic import BaseModel, Field


class BillingItemInput(BaseModel):
    order_item_id: int | None = None
    item_name: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=1000)
    source_status: str
    consumed_quantity: int = Field(ge=0, le=99)
    billed_quantity: int = Field(ge=0, le=99)
    unit_price: float = Field(ge=0, le=100000)
    include_in_bill: bool = True


class BillingSaveRequest(BaseModel):
    items: list[BillingItemInput]
    discount: float = Field(default=0, ge=0, le=100000)


class BillingCheckoutRequest(BaseModel):
    discount: float = Field(default=0, ge=0, le=100000)
    payment_method: str = Field(min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class BillingItemRead(BaseModel):
    id: int | None
    order_item_id: int | None
    item_name: str
    note: str | None
    source_status: str
    consumed_quantity: int
    billed_quantity: int
    unit_price: float
    include_in_bill: bool
    line_total: float


class BillingSummaryRead(BaseModel):
    order_id: int
    table_id: int
    table_name: str
    seat_numbers: list[int]
    seat_label: str
    items: list[BillingItemRead]
    subtotal: float
    discount: float
    final_total: float
    updated_at: datetime | None


class PendingBillingOrderRead(BaseModel):
    order_id: int
    table_id: int
    table_name: str
    seat_numbers: list[int]
    seat_label: str
    status: str
    items_count: int
    subtotal: float
    updated_at: datetime | None

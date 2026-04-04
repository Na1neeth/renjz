from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.billing_item import BillingItem
from app.models.enums import ActivityAction, OrderItemStatus, OrderStatus
from app.models.payment import Payment
from app.models.user import User
from app.services.order_service import add_activity, load_billing_items


MONEY_STEP = Decimal("0.01")


def money(value: float | Decimal | int) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def build_billing_snapshot(order) -> dict:
    existing_items = {item.order_item_id: item for item in load_billing_items(order)}
    lines: list[dict] = []
    updated_at = None

    for item in sorted(order.items, key=lambda row: row.id):
        existing = existing_items.get(item.id)
        if existing:
            line = serialize_billing_line(existing)
            updated_at = max_datetime(updated_at, existing.updated_at)
        else:
            include_in_bill = item.item_status == OrderItemStatus.ACTIVE
            billed_quantity = item.quantity if include_in_bill else 0
            line_total = money(billed_quantity) * money(0)
            line = {
                "id": None,
                "order_item_id": item.id,
                "item_name": item.item_name,
                "note": item.note,
                "source_status": item.item_status.value,
                "consumed_quantity": item.quantity,
                "billed_quantity": billed_quantity,
                "unit_price": 0.0,
                "include_in_bill": include_in_bill,
                "line_total": float(line_total),
            }
        lines.append(line)

    subtotal = sum(
        (
            money(line["billed_quantity"]) * money(line["unit_price"])
            for line in lines
            if line["include_in_bill"]
        ),
        start=Decimal("0.00"),
    )
    subtotal = subtotal.quantize(MONEY_STEP)
    return {
        "order_id": order.id,
        "table_id": order.table.id,
        "table_name": order.table.name,
        "items": lines,
        "subtotal": float(subtotal),
        "discount": 0.0,
        "final_total": float(subtotal),
        "updated_at": updated_at,
    }


def serialize_billing_line(item: BillingItem) -> dict:
    line_total = money(item.billed_quantity) * money(item.unit_price)
    if not item.include_in_bill:
        line_total = money(0)
    return {
        "id": item.id,
        "order_item_id": item.order_item_id,
        "item_name": item.item_name,
        "note": item.note,
        "source_status": item.source_status,
        "consumed_quantity": item.consumed_quantity,
        "billed_quantity": item.billed_quantity,
        "unit_price": float(item.unit_price),
        "include_in_bill": item.include_in_bill,
        "line_total": float(line_total),
    }


def max_datetime(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if current is None:
        return candidate
    if candidate is None:
        return current
    return max(current, candidate)


def save_billing(db: Session, order, billing_input: list[dict], discount: float, actor: User) -> dict:
    if order.status == OrderStatus.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order already closed")
    if order.status != OrderStatus.BILLING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Waiter must send this order to reception first",
        )

    discount_value = money(discount)
    existing_items = {item.order_item_id: item for item in load_billing_items(order)}
    seen_keys: set[int | None] = set()

    for line in billing_input:
        order_item_id = line.get("order_item_id")
        seen_keys.add(order_item_id)
        existing = existing_items.get(order_item_id)
        if existing:
            existing.item_name = line["item_name"].strip()
            existing.note = line.get("note")
            existing.source_status = line["source_status"]
            existing.consumed_quantity = line["consumed_quantity"]
            existing.billed_quantity = line["billed_quantity"]
            existing.unit_price = money(line["unit_price"])
            existing.include_in_bill = line["include_in_bill"]
        else:
            db.add(
                BillingItem(
                    order_id=order.id,
                    order_item_id=order_item_id,
                    item_name=line["item_name"].strip(),
                    note=line.get("note"),
                    source_status=line["source_status"],
                    consumed_quantity=line["consumed_quantity"],
                    billed_quantity=line["billed_quantity"],
                    unit_price=money(line["unit_price"]),
                    include_in_bill=line["include_in_bill"],
                )
            )

    for existing in list(load_billing_items(order)):
        if existing.order_item_id not in seen_keys:
            db.delete(existing)

    order.status = OrderStatus.BILLING
    order.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(order)
    db.expire(order, ["billing_items", "items"])

    snapshot = build_billing_snapshot(order)
    snapshot["discount"] = float(discount_value)
    snapshot["final_total"] = float(max(money(snapshot["subtotal"]) - discount_value, money(0)))
    snapshot["updated_at"] = datetime.now(timezone.utc)

    add_activity(
        db,
        order=order,
        table=order.table,
        actor=actor,
        action_type=ActivityAction.BILLING_SAVED,
        description="Saved manual billing draft",
        details={
            "subtotal": snapshot["subtotal"],
            "discount": snapshot["discount"],
            "final_total": snapshot["final_total"],
        },
    )
    db.flush()
    return snapshot


def checkout_order(
    db: Session,
    order,
    *,
    discount: float,
    payment_method: str,
    notes: str | None,
    actor: User,
) -> dict:
    if order.status == OrderStatus.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order already closed")
    if order.status != OrderStatus.BILLING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Waiter must send this order to reception first",
        )
    if order.payments:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order already paid")

    snapshot = build_billing_snapshot(order)
    subtotal = money(snapshot["subtotal"])
    discount_value = money(discount)
    final_total = max(subtotal - discount_value, money(0))
    now = datetime.now(timezone.utc)

    payment = Payment(
        order_id=order.id,
        subtotal=subtotal,
        discount=discount_value,
        final_total=final_total,
        payment_method=payment_method.strip(),
        notes=notes.strip() if notes else None,
        received_by_id=actor.id,
        paid_at=now,
    )
    db.add(payment)

    order.status = OrderStatus.CLOSED
    order.closed_by_id = actor.id
    order.closed_at = now
    order.updated_at = now
    db.flush()

    add_activity(
        db,
        order=order,
        table=order.table,
        actor=actor,
        action_type=ActivityAction.PAYMENT_COMPLETED,
        description="Payment completed and bill closed",
        details={
            "subtotal": float(subtotal),
            "discount": float(discount_value),
            "final_total": float(final_total),
            "payment_method": payment.payment_method,
        },
    )
    db.flush()

    return {
        "payment_id": payment.id,
        "subtotal": float(subtotal),
        "discount": float(discount_value),
        "final_total": float(final_total),
    }


def list_pending_billing_orders(db: Session) -> list[dict]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.order import Order

    orders = list(
        db.scalars(
            select(Order)
            .where(Order.status == OrderStatus.BILLING)
            .order_by(Order.updated_at.desc(), Order.id.desc())
            .options(
                selectinload(Order.table),
                selectinload(Order.items),
                selectinload(Order.billing_items),
            )
        )
    )

    summaries: list[dict] = []
    for order in orders:
        snapshot = build_billing_snapshot(order)
        summaries.append(
            {
                "order_id": order.id,
                "table_id": order.table.id,
                "table_name": order.table.name,
                "status": order.status.value,
                "items_count": len(order.items),
                "subtotal": snapshot["subtotal"],
                "updated_at": order.updated_at,
            }
        )
    return summaries

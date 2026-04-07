from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.order import Order
from app.models.payment import Payment
from app.services.billing_service import money


def get_business_timezone() -> ZoneInfo:
    settings = get_settings()
    try:
        return ZoneInfo(settings.business_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def resolve_report_window(
    *,
    start_date: date | None,
    end_date: date | None,
    days: int,
) -> tuple[date, date, datetime, datetime, str]:
    tz = get_business_timezone()
    today = datetime.now(tz).date()

    end_date = end_date or today
    if start_date is None:
        start_date = end_date - timedelta(days=max(days, 1) - 1)

    start_at = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(timezone.utc)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return start_date, end_date, start_at, end_at, str(tz)


def build_sales_report(
    db: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    days: int = 7,
) -> dict:
    start_date, end_date, start_at, end_at, timezone_name = resolve_report_window(
        start_date=start_date,
        end_date=end_date,
        days=days,
    )
    business_tz = get_business_timezone()

    payments = list(
        db.scalars(
            select(Payment)
            .where(Payment.paid_at >= start_at, Payment.paid_at < end_at)
            .order_by(Payment.paid_at.desc(), Payment.id.desc())
            .options(selectinload(Payment.order).selectinload(Order.billing_items))
        )
    )

    gross_sales = Decimal("0.00")
    discount_total = Decimal("0.00")
    net_sales = Decimal("0.00")
    payment_methods: dict[str, dict] = {}
    item_summaries: dict[str, dict] = {}
    daily_totals = {
        day: {
            "date": day,
            "closed_bills_count": 0,
            "gross_sales": Decimal("0.00"),
            "discount_total": Decimal("0.00"),
            "net_sales": Decimal("0.00"),
        }
        for day in (start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1))
    }

    for payment in payments:
        paid_on = payment.paid_at.astimezone(business_tz).date()
        gross_sales += money(payment.subtotal)
        discount_total += money(payment.discount)
        net_sales += money(payment.final_total)

        method_key = payment.payment_method.strip().lower() or "other"
        if method_key not in payment_methods:
            payment_methods[method_key] = {
                "payment_method": payment.payment_method.strip() or "Other",
                "closed_bills_count": 0,
                "total_amount": Decimal("0.00"),
            }
        payment_methods[method_key]["closed_bills_count"] += 1
        payment_methods[method_key]["total_amount"] += money(payment.final_total)

        daily_totals[paid_on]["closed_bills_count"] += 1
        daily_totals[paid_on]["gross_sales"] += money(payment.subtotal)
        daily_totals[paid_on]["discount_total"] += money(payment.discount)
        daily_totals[paid_on]["net_sales"] += money(payment.final_total)

        for item in payment.order.billing_items:
            if not item.include_in_bill or item.billed_quantity <= 0:
                continue
            item_key = item.item_name.strip().lower()
            if item_key not in item_summaries:
                item_summaries[item_key] = {
                    "item_name": item.item_name.strip(),
                    "quantity_sold": 0,
                    "revenue": Decimal("0.00"),
                }
            item_summaries[item_key]["quantity_sold"] += item.billed_quantity
            item_summaries[item_key]["revenue"] += money(item.billed_quantity) * money(item.unit_price)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "timezone": timezone_name,
        "closed_bills_count": len(payments),
        "gross_sales": float(gross_sales),
        "discount_total": float(discount_total),
        "net_sales": float(net_sales),
        "payment_methods": [
            {
                "payment_method": entry["payment_method"],
                "closed_bills_count": entry["closed_bills_count"],
                "total_amount": float(entry["total_amount"]),
            }
            for entry in sorted(
                payment_methods.values(),
                key=lambda entry: (-entry["total_amount"], entry["payment_method"].lower()),
            )
        ],
        "items": [
            {
                "item_name": entry["item_name"],
                "quantity_sold": entry["quantity_sold"],
                "revenue": float(entry["revenue"]),
            }
            for entry in sorted(
                item_summaries.values(),
                key=lambda entry: (-entry["quantity_sold"], -entry["revenue"], entry["item_name"].lower()),
            )
        ],
        "daily_totals": [
            {
                "date": day,
                "closed_bills_count": entry["closed_bills_count"],
                "gross_sales": float(entry["gross_sales"]),
                "discount_total": float(entry["discount_total"]),
                "net_sales": float(entry["net_sales"]),
            }
            for day, entry in sorted(daily_totals.items(), reverse=True)
        ],
    }

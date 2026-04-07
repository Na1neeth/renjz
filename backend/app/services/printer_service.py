from decimal import Decimal
import socket

from app.core.config import get_settings
from app.models.enums import OrderStatus
from app.models.payment import Payment
from app.services.billing_service import money
from app.services.order_service import format_seat_label, load_billing_items
from app.services.reporting_service import get_business_timezone


ESC = b"\x1b"
GS = b"\x1d"


def print_receipt_for_payment(order, payment: Payment, *, actor_name: str) -> dict | None:
    settings = get_settings()
    if not settings.receipt_printer_enabled:
        return None

    printer_host = settings.receipt_printer_host.strip()
    if not printer_host:
        return None

    payload = build_receipt_payload(order, payment=payment, actor_name=actor_name)
    try:
        send_to_network_printer(
            payload,
            host=printer_host,
            port=settings.receipt_printer_port,
            timeout_seconds=settings.receipt_printer_timeout_seconds,
        )
    except OSError as exc:
        return {
            "receipt_printed": False,
            "receipt_message": f"{printer_host}:{settings.receipt_printer_port} unreachable: {exc}",
        }

    return {
        "receipt_printed": True,
        "receipt_message": f"Receipt sent to printer at {printer_host}:{settings.receipt_printer_port}.",
    }


def build_receipt_payload(order, *, payment: Payment, actor_name: str) -> bytes:
    settings = get_settings()
    width = max(settings.receipt_printer_chars_per_line, 32)
    seat_label = format_seat_label(sorted({seat.seat_number for seat in order.seats}))
    tz = get_business_timezone()
    paid_at = payment.paid_at.astimezone(tz)

    lines = [ESC + b"@" + line_break()]
    lines.extend(center_text(settings.receipt_header.strip() or "Renjz Kitchen", width=width, emphasized=True))
    lines.append(text_line(divider(width)))
    lines.append(text_line(f"Table : {order.table.name}", width=width))
    lines.append(text_line(f"Seats : {seat_label}", width=width))
    lines.append(text_line(f"Check : {order.id}", width=width))
    lines.append(text_line(f"Date  : {paid_at.strftime('%Y-%m-%d %H:%M')}", width=width))
    lines.append(text_line(divider(width)))

    billed_items = [
        item
        for item in load_billing_items(order)
        if item.include_in_bill and item.billed_quantity > 0
    ]
    if billed_items:
        for item in billed_items:
            lines.extend(render_receipt_item(item.item_name, item.billed_quantity, money(item.unit_price), width=width))
            if item.note:
                lines.append(text_line(f"  Note: {sanitize_text(item.note)}", width=width))
    else:
        lines.append(text_line("No billed items", width=width))

    lines.append(text_line(divider(width)))
    lines.append(two_column_line("Subtotal", format_money(payment.subtotal), width=width))
    if money(payment.discount) > Decimal("0.00"):
        lines.append(two_column_line("Discount", format_money(payment.discount), width=width))
    lines.append(two_column_line("Total", format_money(payment.final_total), width=width, emphasized=True))
    lines.append(text_line(divider(width)))
    lines.append(text_line(f"Paid by : {sanitize_text(payment.payment_method.upper())}", width=width))
    lines.append(text_line(f"Taken by: {sanitize_text(actor_name)}", width=width))
    if payment.notes:
        lines.append(text_line(f"Notes   : {sanitize_text(payment.notes)}", width=width))
    if order.status == OrderStatus.CLOSED:
        lines.append(text_line("Status  : PAID", width=width))
    lines.append(text_line(divider(width)))
    footer = settings.receipt_footer.strip()
    if footer:
        lines.extend(center_text(footer, width=width))
    lines.extend([line_break(), line_break(), cut_paper()])
    return b"".join(lines)


def send_to_network_printer(payload: bytes, *, host: str, port: int, timeout_seconds: float) -> None:
    with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
        connection.sendall(payload)


def render_receipt_item(name: str, quantity: int, unit_price: Decimal, *, width: int) -> list[bytes]:
    line_total = money(quantity) * unit_price
    quantity_label = f"{quantity} x {format_money(unit_price)}"
    item_name = sanitize_text(name)
    first_line = two_column_line(item_name[:width], format_money(line_total), width=width)
    detail_line = text_line(f"  {quantity_label}", width=width)
    return [first_line, detail_line]


def divider(width: int) -> str:
    return "-" * width


def format_money(value: Decimal | float | int) -> str:
    return f"Rs {money(value):.2f}"


def sanitize_text(value: str) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned.encode("ascii", "replace").decode("ascii")


def text_line(value: str = "", *, width: int | None = None) -> bytes:
    if width is not None:
        value = value[:width]
    return sanitize_text(value).encode("ascii", "replace") + b"\n"


def two_column_line(left: str, right: str, *, width: int, emphasized: bool = False) -> bytes:
    left_clean = sanitize_text(left)
    right_clean = sanitize_text(right)
    space_count = max(width - len(left_clean) - len(right_clean), 1)
    content = f"{left_clean}{' ' * space_count}{right_clean}"
    if emphasized:
        return ESC + b"E\x01" + text_line(content, width=width) + ESC + b"E\x00"
    return text_line(content, width=width)


def center_text(value: str, *, width: int, emphasized: bool = False) -> list[bytes]:
    centered = sanitize_text(value)[:width].center(width)
    if emphasized:
        return [ESC + b"a\x01" + ESC + b"E\x01" + text_line(centered) + ESC + b"E\x00" + ESC + b"a\x00"]
    return [ESC + b"a\x01" + text_line(centered) + ESC + b"a\x00"]


def line_break() -> bytes:
    return b"\n"


def cut_paper() -> bytes:
    return GS + b"V\x00"

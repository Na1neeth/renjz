from decimal import Decimal
import shutil
import socket
import subprocess

from app.core.config import get_settings
from app.models.payment import Payment
from app.services.billing_service import money
from app.services.reporting_service import get_business_timezone


ESC = b"\x1b"
GS = b"\x1d"


def print_bill_snapshot(order, snapshot: dict, *, actor_name: str) -> dict | None:
    settings = get_settings()
    if not settings.receipt_printer_enabled:
        return None

    payload = build_bill_payload(order, snapshot=snapshot, actor_name=actor_name)
    return send_receipt_payload(payload, success_label="Bill")


def print_receipt_for_payment(order, payment: Payment, *, actor_name: str) -> dict | None:
    settings = get_settings()
    if not settings.receipt_printer_enabled:
        return None

    payload = build_payment_receipt_payload(order, payment=payment, actor_name=actor_name)
    return send_receipt_payload(payload, success_label="Receipt")


def send_receipt_payload(payload: bytes, *, success_label: str) -> dict:
    settings = get_settings()
    printer_mode = settings.receipt_printer_mode
    if printer_mode == "cups":
        return send_cups_receipt_payload(
            payload,
            printer_name=settings.receipt_printer_name.strip(),
            timeout_seconds=settings.receipt_printer_timeout_seconds,
            success_label=success_label,
        )

    printer_host = settings.receipt_printer_host.strip()
    if not printer_host:
        return {
            "receipt_printed": False,
            "receipt_message": "Receipt printer host is not configured.",
        }

    return send_network_receipt_payload(
        payload,
        host=printer_host,
        port=settings.receipt_printer_port,
        timeout_seconds=settings.receipt_printer_timeout_seconds,
        success_label=success_label,
    )


def send_network_receipt_payload(payload: bytes, *, host: str, port: int, timeout_seconds: float, success_label: str) -> dict:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
            connection.sendall(payload)
    except OSError as exc:
        return {
            "receipt_printed": False,
            "receipt_message": f"{host}:{port} unreachable: {exc}",
        }

    return {
        "receipt_printed": True,
        "receipt_message": f"{success_label} sent to printer at {host}:{port}.",
    }


def send_cups_receipt_payload(payload: bytes, *, printer_name: str, timeout_seconds: float, success_label: str) -> dict:
    if not printer_name:
        return {
            "receipt_printed": False,
            "receipt_message": "Receipt printer name is not configured for CUPS mode.",
        }

    lp_path = shutil.which("lp")
    if not lp_path:
        return {
            "receipt_printed": False,
            "receipt_message": "`lp` command not found on this machine.",
        }

    try:
        completed = subprocess.run(
            [lp_path, "-d", printer_name, "-o", "raw"],
            input=payload,
            capture_output=True,
            timeout=max(timeout_seconds, 1.0),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "receipt_printed": False,
            "receipt_message": f"`lp` timed out while sending data to printer '{printer_name}'.",
        }
    except OSError as exc:
        return {
            "receipt_printed": False,
            "receipt_message": f"Failed to execute `lp` for printer '{printer_name}': {exc}",
        }

    if completed.returncode != 0:
        error_output = completed.stderr.decode("utf-8", "replace").strip() or completed.stdout.decode("utf-8", "replace").strip()
        return {
            "receipt_printed": False,
            "receipt_message": error_output or f"`lp` exited with status {completed.returncode} for printer '{printer_name}'.",
        }

    return {
        "receipt_printed": True,
        "receipt_message": f"{success_label} sent to printer queue '{printer_name}'.",
    }


def build_bill_payload(order, *, snapshot: dict, actor_name: str) -> bytes:
    business_tz = get_business_timezone()
    updated_at = snapshot.get("updated_at") or order.updated_at or order.opened_at
    rendered_at = updated_at.astimezone(business_tz) if updated_at else None
    document_title = "BILL"
    return build_document_payload(
        order,
        title=document_title,
        item_rows=snapshot.get("items", []),
        subtotal=money(snapshot.get("subtotal", 0)),
        discount=money(snapshot.get("discount", 0)),
        final_total=money(snapshot.get("final_total", 0)),
        metadata_lines=[
            f"Table: {order.table.name}",
            f"Seats: {snapshot.get('seat_label', '')}",
            f"Bill No: {order.id}",
            f"Printed: {rendered_at.strftime('%Y-%m-%d %H:%M') if rendered_at else '-'}",
            f"Staff: {actor_name}",
        ],
    )


def build_payment_receipt_payload(order, *, payment: Payment, actor_name: str) -> bytes:
    business_tz = get_business_timezone()
    paid_at = payment.paid_at.astimezone(business_tz)
    item_rows = [
        {
            "item_name": item.item_name,
            "billed_quantity": item.billed_quantity,
            "unit_price": float(item.unit_price),
            "include_in_bill": item.include_in_bill,
        }
        for item in order.billing_items
        if item.include_in_bill and item.billed_quantity > 0
    ]
    payment_title = f"{sanitize_text(payment.payment_method).upper()} RECEIPT"
    return build_document_payload(
        order,
        title=payment_title,
        item_rows=item_rows,
        subtotal=money(payment.subtotal),
        discount=money(payment.discount),
        final_total=money(payment.final_total),
        metadata_lines=[
            f"Table: {order.table.name}",
            f"Seats: {', '.join(str(seat.seat_number) for seat in order.seats)}",
            f"Bill No: {order.id}",
            f"Paid: {paid_at.strftime('%Y-%m-%d %H:%M')}",
            f"Staff: {actor_name}",
        ],
    )


def build_document_payload(
    order,
    *,
    title: str,
    item_rows: list[dict],
    subtotal: Decimal,
    discount: Decimal,
    final_total: Decimal,
    metadata_lines: list[str],
) -> bytes:
    settings = get_settings()
    width = max(settings.receipt_printer_chars_per_line, 32)
    divider = "*" * width

    lines = [initialize_printer()]
    lines.extend(center_big_text(settings.receipt_shop_name.strip() or "RENJZ KITCHEN", width=width))
    lines.append(line_break())
    for line in settings.receipt_address_lines:
        lines.extend(center_text(line, width=width))
    if settings.receipt_phone.strip():
        lines.extend(center_text(f"Telp.: {settings.receipt_phone.strip()}", width=width))
    lines.append(text_line(divider))
    lines.extend(center_text(title, width=width, emphasized=True))
    lines.append(text_line(divider))
    for line in metadata_lines:
        lines.append(text_line(line, width=width))
    if metadata_lines:
        lines.append(text_line(divider))
    lines.append(header_row(width))
    for row in item_rows:
        if not row.get("include_in_bill"):
            continue
        quantity = int(row.get("billed_quantity", 0) or 0)
        if quantity <= 0:
            continue
        item_name = format_item_name(row.get("item_name", ""), quantity)
        line_total = money(quantity) * money(row.get("unit_price", 0))
        lines.extend(item_row(item_name, format_money(line_total), width=width))
    lines.append(text_line(divider))
    if discount > Decimal("0.00"):
        lines.append(left_right_line("Subtotal", format_money(subtotal), width=width))
        lines.append(left_right_line("Discount", format_money(discount), width=width))
    lines.extend(total_row("Total", format_money(final_total), width=width))
    lines.extend([line_break(), line_break()])
    lines.extend(center_text((settings.receipt_footer.strip() or "THANK YOU!").upper(), width=width, emphasized=True))
    lines.extend([line_break(), line_break(), cut_paper()])
    return b"".join(lines)


def format_item_name(name: str, quantity: int) -> str:
    cleaned = sanitize_text(name)
    return f"{cleaned} ({quantity})" if quantity > 1 else cleaned


def format_money(value: Decimal | float | int) -> str:
    return f"Rs {money(value):.2f}"


def header_row(width: int) -> bytes:
    return left_right_line("Description", "Price", width=width, emphasized=True)


def item_row(name: str, price: str, *, width: int) -> list[bytes]:
    price_width = min(max(len(price), 8), 12)
    description_width = max(width - price_width - 1, 12)
    chunks = wrap_text(name, width=description_width)
    rows: list[bytes] = []
    for index, chunk in enumerate(chunks):
        if index == 0:
            rows.append(text_line(f"{chunk.ljust(description_width)} {price.rjust(price_width)}", width=width))
        else:
            rows.append(text_line(chunk, width=width))
    return rows


def total_row(label: str, value: str, *, width: int) -> list[bytes]:
    content = left_right_text(label, value, width=width)
    return [double_size_line(content)]


def left_right_line(left: str, right: str, *, width: int, emphasized: bool = False) -> bytes:
    content = left_right_text(left, right, width=width)
    if emphasized:
        return ESC + b"E\x01" + text_line(content, width=width) + ESC + b"E\x00"
    return text_line(content, width=width)


def left_right_text(left: str, right: str, *, width: int) -> str:
    left_clean = sanitize_text(left)
    right_clean = sanitize_text(right)
    space_count = max(width - len(left_clean) - len(right_clean), 1)
    return f"{left_clean}{' ' * space_count}{right_clean}"


def wrap_text(value: str, *, width: int) -> list[str]:
    text = sanitize_text(value)
    if len(text) <= width:
        return [text]
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word[:width]
    if current:
        lines.append(current)
    return lines or [text[:width]]


def sanitize_text(value: str) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned.encode("ascii", "replace").decode("ascii")


def initialize_printer() -> bytes:
    return ESC + b"@" + ESC + b"a\x00"


def center_text(value: str, *, width: int, emphasized: bool = False) -> list[bytes]:
    centered = sanitize_text(value)[:width].center(width)
    if emphasized:
        return [ESC + b"a\x01" + ESC + b"E\x01" + text_line(centered) + ESC + b"E\x00" + ESC + b"a\x00"]
    return [ESC + b"a\x01" + text_line(centered) + ESC + b"a\x00"]


def center_big_text(value: str, *, width: int) -> list[bytes]:
    centered = sanitize_text(value)[:width].center(width)
    return [ESC + b"a\x01" + GS + b"!\x11" + text_line(centered) + GS + b"!\x00" + ESC + b"a\x00"]


def double_size_line(value: str) -> bytes:
    return GS + b"!\x11" + text_line(value) + GS + b"!\x00"


def text_line(value: str = "", *, width: int | None = None) -> bytes:
    if width is not None:
        value = value[:width]
    return sanitize_text(value).encode("ascii", "replace") + b"\n"


def line_break() -> bytes:
    return b"\n"


def cut_paper() -> bytes:
    return GS + b"V\x00"

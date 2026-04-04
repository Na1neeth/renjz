from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.enums import OrderStatus, UserRole
from app.models.user import User
from app.schemas.billing import (
    BillingCheckoutRequest,
    BillingSaveRequest,
    BillingSummaryRead,
    PendingBillingOrderRead,
)
from app.services.billing_service import (
    build_billing_snapshot,
    checkout_order,
    list_pending_billing_orders,
    save_billing,
)
from app.services.order_service import load_order
from app.websockets.manager import manager


router = APIRouter(prefix="/reception", tags=["reception"])


@router.get("/orders/pending", response_model=list[PendingBillingOrderRead])
def get_pending_bills(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.RECEPTIONIST)),
):
    return list_pending_billing_orders(db)


@router.get("/orders/{order_id}/billing", response_model=BillingSummaryRead)
def get_billing_summary(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.RECEPTIONIST)),
):
    order = load_order(db, order_id)
    if order.status == OrderStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Waiter must send this order to reception first",
        )
    return build_billing_snapshot(order)


@router.put("/orders/{order_id}/billing", response_model=BillingSummaryRead)
async def save_billing_summary(
    order_id: int,
    payload: BillingSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.RECEPTIONIST)),
):
    order = load_order(db, order_id)
    snapshot = save_billing(
        db,
        order,
        billing_input=[item.model_dump() for item in payload.items],
        discount=payload.discount,
        actor=current_user,
    )
    db.commit()
    await manager.broadcast(
        "billing_saved",
        {
            "table_id": order.table.id,
            "order_id": order.id,
            "table_status": order.table.status.value,
            "subtotal": snapshot["subtotal"],
            "discount": snapshot["discount"],
            "final_total": snapshot["final_total"],
        },
    )
    return snapshot


@router.post("/orders/{order_id}/checkout", response_model=dict)
async def complete_checkout(
    order_id: int,
    payload: BillingCheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.RECEPTIONIST)),
):
    order = load_order(db, order_id)
    payment_summary = checkout_order(
        db,
        order,
        discount=payload.discount,
        payment_method=payload.payment_method,
        notes=payload.notes,
        actor=current_user,
    )
    db.commit()
    await manager.broadcast(
        "payment_completed",
        {
            "table_id": order.table.id,
            "order_id": order.id,
            "table_status": order.table.status.value,
            **payment_summary,
        },
    )
    return payment_summary

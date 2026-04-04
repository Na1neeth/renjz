from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.table import TableDetail, TableSummary
from app.services.order_service import (
    list_tables,
    load_table,
    mark_table_empty,
    open_table,
    serialize_table,
)
from app.websockets.manager import manager


router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("", response_model=list[TableSummary])
def get_tables(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return [serialize_table(table) for table in list_tables(db)]


@router.get("/{table_id}", response_model=TableDetail)
def get_table_detail(
    table_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    table = load_table(db, table_id)
    return serialize_table(table)


@router.post("/{table_id}/open", response_model=TableDetail)
async def open_table_for_service(
    table_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.WAITER)),
):
    table = load_table(db, table_id)
    open_table(db, table, current_user)
    db.commit()
    db.refresh(table)
    table = load_table(db, table_id)
    payload = serialize_table(table)
    await manager.broadcast(
        "table_updated",
        {
            "table_id": table.id,
            "order_id": payload["active_order_id"],
            "table_status": table.status.value,
        },
    )
    return payload


@router.post("/{table_id}/mark-empty", response_model=TableDetail)
async def mark_table_available(
    table_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.WAITER)),
):
    table = load_table(db, table_id)
    mark_table_empty(db, table, current_user)
    db.commit()
    db.refresh(table)
    table = load_table(db, table_id)
    payload = serialize_table(table)
    await manager.broadcast(
        "table_emptied",
        {
            "table_id": table.id,
            "order_id": payload["active_order_id"],
            "table_status": table.status.value,
        },
    )
    return payload

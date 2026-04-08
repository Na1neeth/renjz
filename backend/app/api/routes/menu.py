from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.menu import MenuItemCreate, MenuItemRead
from app.services.menu_service import (
    create_menu_item,
    delete_menu_item,
    get_menu_item,
    list_menu_items,
    serialize_menu_item,
)
from app.websockets.manager import manager


router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("", response_model=list[MenuItemRead])
def get_menu(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return [serialize_menu_item(item) for item in list_menu_items(db)]


@router.post("", response_model=MenuItemRead)
async def add_menu_item(
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.KITCHEN)),
):
    item = create_menu_item(db, payload.name)
    db.commit()
    db.refresh(item)
    await manager.broadcast(
        "menu_updated",
        {
            "action": "created",
            "menu_item_id": item.id,
            "item_name": item.name,
        },
    )
    return serialize_menu_item(item)


@router.delete("/{menu_item_id}", response_model=MenuItemRead)
async def remove_menu_item(
    menu_item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.KITCHEN)),
):
    item = get_menu_item(db, menu_item_id)
    payload = serialize_menu_item(item)
    delete_menu_item(db, item)
    db.commit()
    await manager.broadcast(
        "menu_updated",
        {
            "action": "deleted",
            "menu_item_id": payload["id"],
            "item_name": payload["name"],
        },
    )
    return payload

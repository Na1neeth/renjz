from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.menu_item import MenuItem


def normalize_menu_item_name(name: str) -> str:
    return " ".join(str(name or "").strip().split())


def serialize_menu_item(item: MenuItem) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def list_menu_items(db: Session) -> list[MenuItem]:
    return list(
        db.scalars(
            select(MenuItem)
            .execution_options(populate_existing=True)
            .order_by(func.lower(MenuItem.name), MenuItem.id)
        )
    )


def get_menu_item(db: Session, menu_item_id: int) -> MenuItem:
    item = db.get(MenuItem, menu_item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")
    return item


def find_menu_item_by_name(db: Session, name: str) -> MenuItem | None:
    normalized_name = normalize_menu_item_name(name)
    if not normalized_name:
        return None
    return db.scalar(select(MenuItem).where(func.lower(MenuItem.name) == normalized_name.lower()))


def create_menu_item(db: Session, name: str) -> MenuItem:
    normalized_name = normalize_menu_item_name(name)
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Menu item name is required")

    existing = find_menu_item_by_name(db, normalized_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{existing.name} is already on today's menu",
        )

    item = MenuItem(name=normalized_name)
    db.add(item)
    db.flush()
    return item


def delete_menu_item(db: Session, menu_item: MenuItem) -> None:
    db.delete(menu_item)
    db.flush()


def resolve_menu_item_name(
    db: Session,
    name: str,
    *,
    allow_existing_name: str | None = None,
) -> str:
    normalized_name = normalize_menu_item_name(name)
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Menu item name is required")

    if allow_existing_name and normalize_menu_item_name(allow_existing_name).lower() == normalized_name.lower():
        return normalize_menu_item_name(allow_existing_name)

    item = find_menu_item_by_name(db, normalized_name)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose an item from today's menu",
        )
    return item.name

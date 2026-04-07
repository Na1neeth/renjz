from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import UserRole, db_enum


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(db_enum(UserRole, "userrole"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_session_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_session_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    opened_orders = relationship("Order", back_populates="opened_by", foreign_keys="Order.opened_by_id")
    closed_orders = relationship("Order", back_populates="closed_by", foreign_keys="Order.closed_by_id")
    payments_received = relationship("Payment", back_populates="received_by")

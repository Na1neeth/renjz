from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import OrderStatus, db_enum


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"), index=True, nullable=False)
    service_cycle: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        db_enum(OrderStatus, "orderstatus"), default=OrderStatus.RUNNING, nullable=False, index=True
    )
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    table = relationship("RestaurantTable", back_populates="orders")
    opened_by = relationship("User", back_populates="opened_orders", foreign_keys=[opened_by_id])
    closed_by = relationship("User", back_populates="closed_orders", foreign_keys=[closed_by_id])
    items = relationship("OrderItem", back_populates="order", order_by="OrderItem.id")
    activities = relationship("OrderActivityLog", back_populates="order", order_by="OrderActivityLog.id")
    billing_items = relationship("BillingItem", back_populates="order", order_by="BillingItem.id")
    payments = relationship("Payment", back_populates="order", order_by="Payment.id")
    seats = relationship("OrderSeat", back_populates="order", order_by="OrderSeat.seat_number", cascade="all, delete-orphan")

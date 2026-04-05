from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderSeat(Base):
    __tablename__ = "order_seats"
    __table_args__ = (UniqueConstraint("order_id", "seat_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)

    order = relationship("Order", back_populates="seats")

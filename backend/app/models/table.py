from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import TableStatus


class RestaurantTable(TimestampMixin, Base):
    __tablename__ = "tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    status: Mapped[TableStatus] = mapped_column(
        Enum(TableStatus), default=TableStatus.EMPTY, nullable=False, index=True
    )

    orders = relationship("Order", back_populates="table", order_by="Order.id")


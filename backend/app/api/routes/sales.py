from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.billing import SalesReportRead
from app.services.reporting_service import build_sales_report


router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("/reports/sales", response_model=SalesReportRead)
def get_sales_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.SALES)),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start date must be before end date")
    return build_sales_report(db, start_date=start_date, end_date=end_date, days=days)

from datetime import datetime

from pydantic import BaseModel, Field


class MenuItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MenuItemRead(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime

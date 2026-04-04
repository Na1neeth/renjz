from pydantic import BaseModel

from app.models.enums import UserRole


class UserRead(BaseModel):
    id: int
    username: str
    display_name: str
    role: UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


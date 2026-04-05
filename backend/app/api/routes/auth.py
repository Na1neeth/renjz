import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    get_access_token_expiry,
    session_is_active,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.websockets.manager import manager


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username, User.is_active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if session_is_active(user.active_session_key, user.active_session_expires_at):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account is already signed in on another device. Log out there first.",
        )

    expires_at = get_access_token_expiry()
    user.active_session_key = secrets.token_hex(16)
    user.active_session_expires_at = expires_at
    db.commit()
    db.refresh(user)
    await manager.disconnect_user_sessions(user.id)

    token = create_access_token(user.username, user.active_session_key, expires_at)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserRead.model_validate(user, from_attributes=True),
    }


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return UserRead.model_validate(current_user, from_attributes=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.active_session_key = None
    current_user.active_session_expires_at = None
    db.commit()
    await manager.disconnect_user_sessions(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

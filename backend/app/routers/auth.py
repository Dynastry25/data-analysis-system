"""Authentication endpoints: register, login and the current user."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import audit
from app.database import get_db
from app.deps import get_current_user
from app.models import USER_STATUS_ACTIVE, USER_STATUS_SUSPENDED, User
from app.schemas import (
    LoginRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)) -> dict:
    """Create a new account."""
    existing = (
        db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists",
        )

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        status=USER_STATUS_ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.to_dict()


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    """Exchange email + password for a JWT access token."""
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        # The failed attempt is recorded even though the caller is anonymous,
        # because a run of rejected logins is exactly what an operator needs
        # to see. The message stays identical for unknown and wrong-password
        # accounts so it cannot be used to enumerate registered emails.
        audit.record_failure(
            db,
            "auth.login.failed",
            request=request,
            actor_email=payload.email,
            metadata={"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status == USER_STATUS_SUSPENDED:
        audit.record(
            db,
            "auth.login.blocked",
            user=user,
            result=audit.RESULT_DENIED,
            request=request,
            metadata={"reason": "account_suspended"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended. Contact an administrator.",
        )

    user.last_active_at = datetime.now(timezone.utc)
    db.commit()

    audit.record(db, "auth.login", user=user, request=request)
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> dict:
    """Return the signed-in user (used by the frontend to restore a session)."""
    return {**user.to_dict(), "system_role": user.system_role}

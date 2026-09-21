"""Shared FastAPI dependencies: current user + ownership checks."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dataset, User
from app.security import JWTError, decode_token

# auto_error=False so we can raise our own consistent 401 payload.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the Bearer token."""
    if not token:
        raise _credentials_exception()
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise _credentials_exception()

    user = db.get(User, user_id)
    if user is None:
        raise _credentials_exception()
    return user


def get_owned_dataset(
    dataset_id: int, db: Session, user: User, *, require_file: bool = True
) -> Dataset:
    """Fetch a dataset and make sure it belongs to ``user``.

    Every dataset endpoint goes through this so users can only ever see their own
    data (privacy requirement from the spec).
    """
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="You do not have access to this dataset"
        )
    if require_file and not dataset.storage_path:
        raise HTTPException(
            status_code=409, detail="Dataset file is not available on the server"
        )
    return dataset

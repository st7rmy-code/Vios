"""Зависимости FastAPI: сессия, текущий пользователь, проверка ролей и арендатора.

ВРЕМЕННО: матрица прав — допущение до получения раздела «Роли и права».
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Role, User
from app.security import read_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_session)) -> User:
    uid = read_token(token)
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужен вход", headers={"WWW-Authenticate": "Bearer"})
    return user


def require(*roles: Role) -> Callable[..., User]:
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return dep


def check_business(user: User, business_id: uuid.UUID) -> None:
    """Админ видит все бизнесы, остальные только свой. Чужое — 404, чтобы не раскрывать наличие."""
    if user.role is Role.admin:
        return
    if user.business_id != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Не найдено")

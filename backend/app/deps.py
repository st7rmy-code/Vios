"""Зависимости FastAPI: сессия, текущий пользователь, роли и арендатор (спецификация, раздел 1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import ApiError
from app.models import Role, User
from app.security import read_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def current_user(token: str | None = Depends(oauth2), db: Session = Depends(get_session)) -> User:
    uid = read_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if user is None or not user.is_active:
        raise ApiError(401, "Нужен вход", "unauthorized", headers={"WWW-Authenticate": "Bearer"})
    return user


def require(*roles: Role) -> Callable[..., User]:
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise ApiError(403, "Недостаточно прав", "forbidden")
        return user

    return dep


def check_business(user: User, business_id: uuid.UUID | None) -> None:
    """Админ видит все бизнесы, остальные только свой. Чужое — 404, чтобы не раскрывать наличие."""
    if user.role is Role.admin:
        return
    if business_id is None or user.business_id != business_id:
        raise ApiError(404, "Не найдено", "not_found")


def business_for(user: User, business_id: uuid.UUID | None) -> uuid.UUID:
    """Бизнес запроса: свой для owner/executor, явный business_id для admin."""
    bid = business_id or user.business_id
    if bid is None:
        raise ApiError(422, "Укажите бизнес", "business_required")
    check_business(user, bid)
    return bid

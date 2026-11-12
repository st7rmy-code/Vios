"""Бизнесы и команда (спецификация, 5.1)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import business_for, check_business, require
from app.errors import ERROR_RESPONSES, ApiError
from app.models import Business, Role, User
from app.schemas import BusinessCreate, BusinessOut, UserCreate, UserOut
from app.security import hash_password
from app.services import audit

router = APIRouter(tags=["team"], responses=ERROR_RESPONSES)


@router.post("/businesses", response_model=BusinessOut, status_code=201, operation_id="createBusiness")
def create_business(body: BusinessCreate, db: Session = Depends(get_session),
                    user: User = Depends(require(Role.admin))) -> Business:
    b = Business(name=body.name)
    db.add(b)
    db.flush()
    audit.append(db, action="business.created", entity_type="business", entity_id=str(b.id),
                 payload={"name": b.name}, business_id=b.id, actor_id=user.id)
    db.commit()
    return b


@router.get("/businesses", response_model=list[BusinessOut], operation_id="listBusinesses")
def list_businesses(db: Session = Depends(get_session), _: User = Depends(require(Role.admin))) -> list[Business]:
    return list(db.execute(select(Business).order_by(Business.name)).scalars())


@router.post("/users", response_model=UserOut, status_code=201, operation_id="createUser")
def create_user(body: UserCreate, db: Session = Depends(get_session),
                user: User = Depends(require(Role.admin, Role.owner))) -> User:
    if user.role is Role.owner:
        if body.role is not Role.executor:
            raise ApiError(403, "Собственник может добавлять только исполнителей", "role_not_allowed")
        body.business_id = user.business_id
    if body.role is not Role.admin and body.business_id is None:
        raise ApiError(422, "Укажите бизнес", "business_required")
    if body.business_id is not None and db.get(Business, body.business_id) is None:
        raise ApiError(404, "Бизнес не найден", "not_found")
    if db.execute(select(User.id).where(User.login == body.login)).first():
        raise ApiError(409, "Такой логин уже есть", "login_taken")
    u = User(login=body.login, password_hash=hash_password(body.password), role=body.role,
             business_id=body.business_id if body.role is not Role.admin else None)
    db.add(u)
    db.flush()
    audit.append(db, action="user.created", entity_type="user", entity_id=str(u.id),
                 payload={"login": u.login, "role": u.role.value}, business_id=u.business_id, actor_id=user.id)
    db.commit()
    return u


@router.get("/users", response_model=list[UserOut], operation_id="listUsers")
def list_users(business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
               user: User = Depends(require(Role.admin, Role.owner))) -> list[User]:
    q = select(User).order_by(User.created_at)
    if user.role is Role.admin and business_id is None:
        return list(db.execute(q).scalars())
    bid = business_for(user, business_id)
    return list(db.execute(q.where(User.business_id == bid)).scalars())


@router.post("/users/{user_id}/deactivate", response_model=UserOut, operation_id="deactivateUser")
def deactivate_user(user_id: uuid.UUID, db: Session = Depends(get_session),
                    user: User = Depends(require(Role.admin, Role.owner))) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise ApiError(404, "Не найдено", "not_found")
    check_business(user, target.business_id)
    if user.role is Role.owner and target.role is not Role.executor:
        raise ApiError(403, "Собственник может отключать только исполнителей", "role_not_allowed")
    if target.id == user.id:
        raise ApiError(409, "Нельзя отключить самого себя", "self_deactivate")
    if target.is_active:
        target.is_active = False
        audit.append(db, action="user.deactivated", entity_type="user", entity_id=str(target.id),
                     payload={"login": target.login}, business_id=target.business_id, actor_id=user.id)
        db.commit()
    return target

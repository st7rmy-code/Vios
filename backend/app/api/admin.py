from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import require
from app.models import Business, Role, User
from app.schemas import BusinessCreate, BusinessOut, UserCreate, UserOut
from app.security import hash_password
from app.services import audit

router = APIRouter(tags=["admin"])


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


@router.post("/users", response_model=UserOut, status_code=201, operation_id="createUser")
def create_user(body: UserCreate, db: Session = Depends(get_session),
                user: User = Depends(require(Role.admin, Role.owner))) -> User:
    if user.role is Role.owner:
        # собственник заводит только исполнителей своего бизнеса
        if body.role is not Role.executor:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Собственник может добавлять только исполнителей")
        body.business_id = user.business_id
    if body.role is not Role.admin and body.business_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите бизнес")
    u = User(login=body.login, password_hash=hash_password(body.password), role=body.role,
             business_id=body.business_id)
    db.add(u)
    db.flush()
    audit.append(db, action="user.created", entity_type="user", entity_id=str(u.id),
                 payload={"login": u.login, "role": u.role.value}, business_id=u.business_id, actor_id=user.id)
    db.commit()
    return u

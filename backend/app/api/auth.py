from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.db import get_session
from app.deps import current_user
from app.errors import ERROR_RESPONSES, ApiError
from app.models import Business, User
from app.schemas import MeOut, Token
from app.security import issue_token, verify_password
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)


@router.post("/token", response_model=Token, operation_id="login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)) -> Token:
    user = db.execute(select(User).where(User.login == form.username)).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        # логин не пишем целиком: это может быть опечатка с чужими данными
        audit.append(db, action="auth.login_failed", entity_type="user",
                     entity_id=str(user.id) if user else None,
                     payload={"reason": "inactive" if user and not user.is_active else "bad_credentials"},
                     business_id=user.business_id if user else None)
        db.commit()
        raise ApiError(401, "Неверный логин или пароль", "bad_credentials")
    user.last_login_at = clock.now()
    db.commit()
    return Token(access_token=issue_token(user.id))


@router.get("/me", response_model=MeOut, operation_id="me")
def me(user: User = Depends(current_user), db: Session = Depends(get_session)) -> MeOut:
    out = MeOut.model_validate(user)
    if user.business_id:
        b = db.get(Business, user.business_id)
        out.business_name, out.business_timezone = b.name, b.timezone
    return out

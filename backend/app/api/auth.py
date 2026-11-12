from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import current_user
from app.models import User
from app.schemas import Token, UserOut
from app.security import issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token, operation_id="login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)) -> Token:
    user = db.execute(select(User).where(User.login == form.username)).scalar_one_or_none()
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    return Token(access_token=issue_token(user.id))


@router.get("/me", response_model=UserOut, operation_id="me")
def me(user: User = Depends(current_user)) -> User:
    return user

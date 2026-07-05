import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from fastapi import HTTPException
from app.core.security import (
    verify_password,
    create_access_token
)
from app.schemas.user import UserLogin
from fastapi.security import OAuth2PasswordRequestForm

from app.core.security import (
    oauth2_scheme,
    verify_access_token
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/users")
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    normalized_email = user_data.email.lower()

    existing_username = db.query(User).filter(
        User.username == user_data.username
    ).first()
    if existing_username:
        logger.warning("Registration conflict: username %r already exists", user_data.username)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken"
        )

    existing_email = db.query(User).filter(
        func.lower(User.email) == normalized_email
    ).first()
    if existing_email:
        logger.warning("Registration conflict: email %r already exists", normalized_email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )

    user = User(
        username=user_data.username,
        email=normalized_email,
        hashed_password=hash_password(user_data.password)
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning(
            "Registration integrity error for username=%r email=%r",
            user_data.username,
            normalized_email,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists"
        )
    db.refresh(user)

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "karma": user.karma
    }
@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        (func.lower(User.email) == form_data.username.lower()) |
        (User.username == form_data.username)
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not verify_password(
        form_data.password,
        user.hashed_password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    access_token = create_access_token(
        data={"sub": user.email}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    email = verify_access_token(token)

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    return user

@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user)
):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "karma": current_user.karma,
        "role": current_user.role,
        "is_admin": current_user.is_admin,
        "is_owner": current_user.is_owner,
        "is_head_admin": current_user.is_head_admin
    }

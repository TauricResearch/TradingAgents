from typing import Optional
from sqlmodel import Session, select
from app.domain.models import User
from app.core.schemas.user import UserCreate, UserUpdate
from app.domain.repositories import IUserRepository
from app.core.security import get_password_hash

class UserRepository(IUserRepository):
    def __init__(self, db: Session):
        self.db = db

    def get(self, id: int) -> Optional[User]:
        return self.db.get(User, id)

    def get_by_email(self, *, email: str) -> Optional[User]:
        statement = select(User).where(User.email == email)
        return self.db.exec(statement).first()

    def get_multi(self, *, skip: int = 0, limit: int = 100) -> list[User]:
        statement = select(User).offset(skip).limit(limit)
        return self.db.exec(statement).all()

    def create(self, *, obj_in: UserCreate) -> User:
        db_obj = User(
            email=obj_in.email,
            username=obj_in.username,
            hashed_password=get_password_hash(obj_in.password),
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
        )
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def update(self, *, db_obj: User, obj_in: UserUpdate) -> User:
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def remove(self, *, id: int) -> User:
        db_obj = self.db.get(User, id)
        self.db.delete(db_obj)
        self.db.commit()
        return db_obj

    def is_superuser(self, *, user: User) -> bool:
        return user.is_superuser

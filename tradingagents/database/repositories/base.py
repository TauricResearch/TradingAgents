from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from tradingagents.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, session: Session, model_class: type[ModelType]):
        self.session = session
        self.model_class = model_class

    def get(self, id: UUID | str | int) -> ModelType | None:
        return (
            self.session.query(self.model_class)
            .filter(self.model_class.id == id)
            .first()
        )

    def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        return self.session.query(self.model_class).offset(skip).limit(limit).all()

    def create(self, obj_in: dict) -> ModelType:
        db_obj = self.model_class(**obj_in)
        self.session.add(db_obj)
        self.session.flush()
        return db_obj

    def update(self, db_obj: ModelType, obj_in: dict) -> ModelType:
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        self.session.flush()
        return db_obj

    def delete(self, id: UUID | str | int) -> bool:
        obj = self.get(id)
        if obj:
            self.session.delete(obj)
            return True
        return False

    def count(self) -> int:
        return self.session.query(self.model_class).count()

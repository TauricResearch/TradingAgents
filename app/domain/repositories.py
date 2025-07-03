from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List
from sqlmodel import SQLModel
from app.core.schemas.user import UserCreate, UserUpdate
from app.domain.models import User

ModelType = TypeVar("ModelType", bound=SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)

class IRepository(Generic[ModelType], ABC):
    @abstractmethod
    def get(self, id: int) -> Optional[ModelType]:
        pass

    @abstractmethod
    def get_multi(self, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        pass

    @abstractmethod
    def create(self, *, obj_in: CreateSchemaType) -> ModelType:
        pass

    @abstractmethod
    def update(self, *, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        pass

    @abstractmethod
    def remove(self, *, id: int) -> ModelType:
        pass


class IUserRepository(IRepository[User], ABC):
    @abstractmethod
    def get_by_email(self, *, email: str) -> Optional[User]:
        pass

    @abstractmethod
    def create(self, *, obj_in: UserCreate) -> User:
        pass

    @abstractmethod
    def update(self, *, db_obj: User, obj_in: UserUpdate) -> User:
        pass

    @abstractmethod
    def is_superuser(self, *, user: User) -> bool:
        pass

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from app.api import deps
from app.core.schemas.user import User, UserCreate, UserUpdate
from app.domain.models import User as UserModel
from app.domain.repositories import IUserRepository

router = APIRouter()

@router.get("/", response_model=List[User])
def read_users(
    repo: IUserRepository = Depends(deps.get_user_repository),
    skip: int = 0,
    limit: int = 100,
    current_user: UserModel = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve users.
    """
    users = repo.get_multi(skip=skip, limit=limit)
    return users

@router.post("/", response_model=User)
def create_user(
    *,
    repo: IUserRepository = Depends(deps.get_user_repository),
    user_in: UserCreate,
    current_user: UserModel = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new user.
    """
    user = repo.get_by_email(email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    user = repo.create(obj_in=user_in)
    return user

@router.get("/me", response_model=User)
def read_user_me(
    current_user: UserModel = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get current user.
    """
    return current_user

@router.get("/{user_id}", response_model=User)
def read_user_by_id(
    user_id: int,
    repo: IUserRepository = Depends(deps.get_user_repository),
    current_user: UserModel = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get a specific user by id.
    """
    user = repo.get(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        return user
    if not repo.is_superuser(user=current_user):
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return user

@router.put("/{user_id}", response_model=User)
def update_user(
    *,
    repo: IUserRepository = Depends(deps.get_user_repository),
    user_id: int,
    user_in: UserUpdate,
    current_user: UserModel = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a user.
    """
    user = repo.get(id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this username does not exist in the system",
        )
    user = repo.update(db_obj=user, obj_in=user_in)
    return user

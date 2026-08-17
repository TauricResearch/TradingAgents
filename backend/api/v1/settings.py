import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.deps import get_current_user
from backend.models import User
from backend.schemas import SettingsIn
from backend.services.auth import user_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(user: User = Depends(get_current_user)):
    return user_settings(user)


@router.put("")
def put_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    current = user_settings(user)
    current.update(body.model_dump())
    user.settings_json = json.dumps(current)
    db.add(user)
    db.commit()
    return current

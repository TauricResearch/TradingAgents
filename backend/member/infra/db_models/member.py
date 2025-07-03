from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, UUID, Numeric, VARCHAR  # 필요한 타입들을 sqlalchemy에서 가져옵니다.
from utils.auth import Role
import uuid


class Member(SQLModel, table=True):
    __tablename__ = "members"
    id : str = Field(default=None, max_length=36, primary_key=True)
    email : str = Field(max_length=64, unique=True, nullable=False)
    name : str = Field(max_length=32, nullable=False)
    password : str = Field(max_length=64, nullable=False)
    is_active : bool = Field(default=True, nullable=False)
    created_at : datetime = Field(nullable=False)
    updated_at : datetime = Field(nullable=False)
    role : Role = Field(default=Role.USER, nullable=False)
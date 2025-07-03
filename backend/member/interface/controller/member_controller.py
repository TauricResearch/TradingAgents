from fastapi import APIRouter, status, Depends
from member.interface.dto import CreateUserBody, MemberResponse
from member.application.member_service import MemberService
from typing import Annotated
from utils.containers import Container


router = APIRouter(prefix="/users", tags=["users"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=MemberResponse)
async def create_user(
    member: CreateUserBody,
    member_service: Annotated[MemberService, Depends(Container.member_service)]
):
    created_member = member_service.create_member(
        member.name,
        member.email,
        member.password,
        member.role
    )
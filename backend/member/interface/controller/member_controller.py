from fastapi import APIRouter, status, Depends,HTTPException
from member.interface.dto import CreateUserBody, MemberResponse
from member.application.member_service import MemberService
from typing import Annotated
from utils.containers import Container
from dependency_injector.wiring import inject, Provide
from fastapi.security import OAuth2PasswordRequestForm
from utils.auth import get_current_member, CurrentMember, get_admin_member

router = APIRouter(prefix="/members", tags=["members"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=MemberResponse)
@inject
async def create_user(
    member: CreateUserBody,
    member_service: MemberService = Depends(Provide[Container.member_service])
):
    created_member = member_service.create_member(
        member.name,
        member.email,
        member.password,
        member.role
    )

    return created_member

@router.post("/login")
@inject
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    member_service: MemberService = Depends(Provide[Container.member_service])
):
    access_token = member_service.login(
        email=form_data.username,
        password=form_data.password
    )

    return {
        "access_token" : access_token,
        "token_type" : "Bearer"
    }

@router.get("/me", response_model=dict)
def get_current_user_info(
    current_user: CurrentMember = Depends(get_current_member)
):
    """
    현재 로그인한 사용자 정보를 조회합니다.
    이 엔드포인트는 JWT 토큰이 필요하며, Swagger UI에서 Authorize 버튼을 활성화합니다.
    """
    return {
        "user_id": current_user.id,
        "role": current_user.role,
        "message": "Successfully authenticated"
    }

@router.get("/{member_id}", response_model=MemberResponse)
@inject
def get_member(
    member_id: str,
    current_member: Annotated[CurrentMember | None, Depends(get_current_member)] = None,
    member_service: Annotated[MemberService | None, Depends(Provide[Container.member_service])] = None
):

    member = member_service.get_member(member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return member

# @router.get("/analysis-sessions", response_model=list[AnalysisSessionResponse])
# @inject
# def get_member_analysis_sessions(
#     current_member: Annotated[CurrentMember | None, Depends(get_current_member)] = None,
#     member_service: Annotated[MemberService | None, Depends(Provide[Container.member_service])] = None
# ):
    
#     result = member_service.get_analysis_sessions_by_member(current_member.id)
#     return result

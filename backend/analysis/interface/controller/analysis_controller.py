from typing import Annotated
from fastapi import APIRouter, Depends, BackgroundTasks
from analysis.interface.dto import AnalysisSessionResponse
from utils.auth import get_current_member, CurrentMember
from dependency_injector.wiring import inject, Provide
from analysis.application.analysis_service import AnalysisService
from utils.containers import Container

router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.get("/")
@inject
def get_analysis_list_for_member(
    current_member : Annotated[CurrentMember, Depends(get_current_member)],
    analysis_service: Annotated[AnalysisService, Depends(Provide[Container.analysis_service])]
):
    """
    현재 로그인한 사용자의 모든 분석 세션 목록을 조회합니다.
    """
    return analysis_service.get_analysis_list(current_member.id)

@router.post("/start", status_code=201)
@inject
def start_analysis_session(
    current_member : Annotated[CurrentMember, Depends(get_current_member)],
    analysis_service: Annotated[AnalysisService, Depends(Provide[Container.analysis_service])],
    background_tasks: BackgroundTasks
):
    """
    새로운 분석 세션을 시작합니다.
    """
    new_analysis = analysis_service.create_analysis(current_member.id, background_tasks)
    return new_analysis



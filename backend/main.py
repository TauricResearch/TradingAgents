from fastapi import FastAPI
from utils.database import create_db_and_tables
from utils.containers import Container

from analysis.interface.controller.analysis_controller import router as analysis_router
from member.interface.controller.member_controller import router as member_router
import logging
from utils.logger import setup_logging

setup_logging()



app = FastAPI()
app.container = Container()

app.include_router(analysis_router)
app.include_router(member_router)

@app.on_event("startup")
def startup_db_client():
    logger = logging.getLogger(__name__)
    logger.info("🚀 FastAPI 애플리케이션 시작")
    create_db_and_tables()
    logger.info("📊 데이터베이스 초기화 완료")

@app.get("/")
def root():
    logger = logging.getLogger(__name__)
    logger.info("📍 루트 엔드포인트 호출됨")
    return {"message": "Trading Agents API"}
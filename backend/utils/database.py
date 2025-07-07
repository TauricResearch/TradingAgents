import os
from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session
from config.config import get_settings
from member.infra.db_models.member import Member
from analysis.infra.db_models.analysis import Analysis
import logging

class DatabaseConnectionError(Exception):
    """데이터베이스 연결 오류"""
    pass

logger = logging.getLogger(__name__)
settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent.parent

# 데이터베이스 연결 설정 개선
engine_config = {
    "echo": settings.DEBUG,  # 프로덕션에서는 SQL 로그 비활성화
    "pool_size": 10,  # 연결 풀 크기
    "max_overflow": 20,  # 최대 초과 연결 수
    "pool_pre_ping": True,  # 연결 상태 확인
    "pool_recycle": 3600,  # 1시간마다 연결 재사용
    "connect_args": {
        "charset": "utf8mb4",
        "connect_timeout": 10,
        "read_timeout": 30,
        "write_timeout": 30,
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
    }
}

# MySQL 엔진 생성
try:
    engine = create_engine(settings.database_url, **engine_config)
    logger.info("데이터베이스 엔진 생성 완료")
except Exception as e:
    logger.error(f"데이터베이스 엔진 생성 실패: {str(e)}")
    raise DatabaseConnectionError()

def get_session():
    """데이터베이스 세션 생성"""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"데이터베이스 트랜잭션 실패: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()

def create_db_and_tables():
    """테이블 생성"""
    try:
        # 개발 환경에서만 테이블 자동 생성
        if not settings.is_production:
            SQLModel.metadata.create_all(engine)
            logger.info("데이터베이스 테이블 생성 완료")
        else:
            logger.info("프로덕션 환경 - 테이블 자동 생성 건너뜀")
    except Exception as e:
        logger.error(f"테이블 생성 실패: {str(e)}")
        raise DatabaseConnectionError()

def check_db_connection():
    """데이터베이스 연결 확인"""
    try:
        with Session(engine) as session:
            session.exec("SELECT 1")
        logger.info("데이터베이스 연결 확인 완료")
        return True
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {str(e)}")
        return False

if __name__ == "__main__":
    create_db_and_tables()
    if check_db_connection():
        print("✅ 데이터베이스 연결 성공")
    else:
        print("❌ 데이터베이스 연결 실패") 
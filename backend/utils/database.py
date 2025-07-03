import os
from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session
from config.config import get_settings
from analysis_session.infra.db_models.analysis_session import AnalysisSession
from member.infra.db_models.member import Member

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent.parent
print(settings)
# MySQL 데이터베이스 URL 구성
DATABASE_URL = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset=utf8mb4"

# MySQL 엔진 생성
engine = create_engine(
    DATABASE_URL, 
    echo=True
)

def get_session():
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    # 테이블 생성
    # SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

if __name__ == "__main__":
    create_db_and_tables()
    print(DATABASE_URL) 
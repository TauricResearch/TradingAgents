import sys
import logging
import colorlog
from typing import Optional


# 강화된 컬러 로깅 설정
def setup_logging():
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 컬러 콘솔 핸들러 생성
    console_handler = colorlog.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # 컬러 포맷터 설정
    color_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )
    console_handler.setFormatter(color_formatter)
    
    # 핸들러 추가
    root_logger.addHandler(console_handler)
    
    # FastAPI/uvicorn 로거 설정
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    
    # 애플리케이션 로거들 설정
    logging.getLogger("analysis").setLevel(logging.INFO)
    logging.getLogger("analysis.application").setLevel(logging.INFO)
    logging.getLogger("analysis.application.analysis_service").setLevel(logging.INFO)
    
    # 로깅 설정 완료 메시지
    logger = logging.getLogger(__name__)
    logger.info("✅ 컬러 로깅 설정 완료")


def get_colored_logger(
    name: str,
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    컬러 로거를 가져오는 함수
    
    Args:
        name: 로거 이름
        level: 로깅 레벨
        format_string: 커스텀 포맷 문자열
    
    Returns:
        설정된 컬러 로거
    """
    
    # 기본 포맷 설정
    if format_string is None:
        format_string = (
            "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    # 컬러 포맷터 생성
    color_formatter = colorlog.ColoredFormatter(
        format_string,
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )
    
    # 로거 생성
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 이미 핸들러가 있으면 기존 로거 반환
    if logger.handlers:
        return logger
    
    # 콘솔 핸들러 생성
    console_handler = colorlog.StreamHandler()
    console_handler.setFormatter(color_formatter)
    console_handler.setLevel(level)
    
    # 핸들러 추가
    logger.addHandler(console_handler)
    
    # 상위 로거로 전파 방지
    logger.propagate = False
    
    return logger
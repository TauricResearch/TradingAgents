from fastapi import HTTPException, status
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class BaseAPIException(HTTPException):
    """기본 API 예외 클래스"""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code or self.__class__.__name__
        logger.error(f"API Exception: {self.error_code} - {detail}")

# 인증/권한 관련 예외
class AuthenticationError(BaseAPIException):
    """인증 실패 예외"""
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="AUTH_001"
        )

class AuthorizationError(BaseAPIException):
    """권한 부족 예외"""
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="AUTH_002"
        )

class InvalidTokenError(BaseAPIException):
    """토큰 오류 예외"""
    def __init__(self, detail: str = "Invalid or expired token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="AUTH_003"
        )

# 비즈니스 로직 관련 예외
class ResourceNotFoundError(BaseAPIException):
    """리소스 찾을 수 없음 예외"""
    def __init__(self, resource_type: str, resource_id: str = None):
        detail = f"{resource_type} not found"
        if resource_id:
            detail += f" (ID: {resource_id})"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code="BIZ_001"
        )

class DuplicateResourceError(BaseAPIException):
    """중복 리소스 예외"""
    def __init__(self, resource_type: str, field: str = None):
        detail = f"{resource_type} already exists"
        if field:
            detail += f" (field: {field})"
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="BIZ_002"
        )

class ValidationError(BaseAPIException):
    """입력 검증 실패 예외"""
    def __init__(self, detail: str = "Validation failed", field: str = None):
        if field:
            detail = f"Validation failed for field: {field} - {detail}"
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            error_code="VAL_001"
        )

class BusinessLogicError(BaseAPIException):
    """비즈니스 로직 오류 예외"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="BIZ_003"
        )

# 분석 관련 예외
class AnalysisError(BaseAPIException):
    """분석 실행 오류 예외"""
    def __init__(self, detail: str = "Analysis execution failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="ANALYSIS_001"
        )

class AnalysisNotFoundError(ResourceNotFoundError):
    """분석 세션 찾을 수 없음 예외"""
    def __init__(self, analysis_id: str = None):
        super().__init__("Analysis", analysis_id)
        self.error_code = "ANALYSIS_002"

class AnalysisAccessDeniedError(AuthorizationError):
    """분석 접근 권한 없음 예외"""
    def __init__(self, analysis_id: str = None):
        detail = "Access denied to analysis"
        if analysis_id:
            detail += f" (ID: {analysis_id})"
        super().__init__(detail)
        self.error_code = "ANALYSIS_003"

# 멤버 관련 예외
class MemberNotFoundError(ResourceNotFoundError):
    """멤버 찾을 수 없음 예외"""
    def __init__(self, member_id: str = None):
        super().__init__("Member", member_id)
        self.error_code = "MEMBER_001"

class MemberAlreadyExistsError(DuplicateResourceError):
    """멤버 이미 존재 예외"""
    def __init__(self, field: str = "email"):
        super().__init__("Member", field)
        self.error_code = "MEMBER_002"

class InvalidCredentialsError(BaseAPIException):
    """잘못된 로그인 정보 예외"""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            error_code="MEMBER_003"
        )

# 데이터베이스 관련 예외
class DatabaseError(BaseAPIException):
    """데이터베이스 오류 예외"""
    def __init__(self, detail: str = "Database operation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="DB_001"
        )

class DatabaseConnectionError(DatabaseError):
    """데이터베이스 연결 오류 예외"""
    def __init__(self):
        super().__init__("Database connection failed")
        self.error_code = "DB_002"

# 외부 서비스 관련 예외
class ExternalServiceError(BaseAPIException):
    """외부 서비스 오류 예외"""
    def __init__(self, service_name: str, detail: str = "External service error"):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{service_name}: {detail}",
            error_code="EXT_001"
        )

class TradingAgentsServiceError(ExternalServiceError):
    """TradingAgents 서비스 오류 예외"""
    def __init__(self, detail: str = "TradingAgents service error"):
        super().__init__("TradingAgents", detail)
        self.error_code = "EXT_002"

# 에러 핸들러 유틸리티
def handle_database_error(e: Exception, operation: str = "database operation") -> DatabaseError:
    """데이터베이스 예외를 처리하고 적절한 예외로 변환"""
    logger.error(f"Database error during {operation}: {str(e)}", exc_info=True)
    
    # 특정 데이터베이스 오류를 더 구체적인 예외로 변환
    error_message = str(e).lower()
    
    if "connection" in error_message:
        return DatabaseConnectionError()
    elif "duplicate" in error_message or "unique constraint" in error_message:
        return DuplicateResourceError("Resource", "unique field")
    elif "foreign key" in error_message:
        return ValidationError("Referenced resource does not exist")
    else:
        return DatabaseError(f"Database operation failed: {operation}")

def handle_validation_error(e: Exception, field: str = None) -> ValidationError:
    """입력 검증 예외를 처리"""
    logger.warning(f"Validation error: {str(e)}")
    return ValidationError(str(e), field)

def handle_business_logic_error(e: Exception, context: str = None) -> BusinessLogicError:
    """비즈니스 로직 예외를 처리"""
    detail = str(e)
    if context:
        detail = f"{context}: {detail}"
    logger.error(f"Business logic error: {detail}")
    return BusinessLogicError(detail)
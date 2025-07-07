from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp
import time
import logging
from typing import Callable, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """보안 헤더 추가 미들웨어"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # 보안 헤더 추가
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com"
        
        return response

class LoggingMiddleware(BaseHTTPMiddleware):
    """요청/응답 로깅 미들웨어"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # 요청 로깅
        logger.info(
            f"Request started: {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )
        
        try:
            response = await call_next(request)
            
            # 응답 로깅
            process_time = time.time() - start_time
            logger.info(
                f"Request completed: {request.method} {request.url.path} "
                f"- Status: {response.status_code} - Duration: {process_time:.4f}s"
            )
            
            response.headers["X-Process-Time"] = str(process_time)
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"- Error: {str(e)} - Duration: {process_time:.4f}s"
            )
            raise

class RateLimitMiddleware(BaseHTTPMiddleware):
    """간단한 Rate Limiting 미들웨어"""
    
    def __init__(self, app: ASGIApp, requests_per_minute: int = 100, period: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.period = period
        self.requests: Dict[str, list] = {}
    
    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 주소 획득"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def _clean_old_requests(self, client_ip: str) -> None:
        """오래된 요청 기록 정리"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.period)
        
        if client_ip in self.requests:
            self.requests[client_ip] = [
                req_time for req_time in self.requests[client_ip]
                if req_time > cutoff
            ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = self._get_client_ip(request)
        now = datetime.now()
        
        # 오래된 요청 정리
        self._clean_old_requests(client_ip)
        
        # 해당 클라이언트의 요청 목록 초기화
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        current_requests = len(self.requests[client_ip])
        
        if current_requests >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for client: {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Max {self.requests_per_minute} requests per {self.period} seconds.",
                    "retry_after": self.period
                }
            )
        
        # 현재 요청 기록
        self.requests[client_ip].append(now)
        
        response = await call_next(request)
        
        # Rate limit 정보 헤더 추가
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(self.requests_per_minute - current_requests - 1)
        response.headers["X-RateLimit-Reset"] = str(int((now + timedelta(seconds=self.period)).timestamp()))
        
        return response

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """전역 에러 핸들링 미들웨어"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            return response
        except HTTPException as e:
            # HTTPException은 FastAPI에서 자동으로 처리되므로 다시 raise
            raise e
        except Exception as e:
            logger.error(f"Unhandled error in request {request.method} {request.url.path}: {str(e)}", exc_info=True)
            
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal Server Error",
                    "message": "An unexpected error occurred. Please try again later.",
                    "request_id": getattr(request.state, 'request_id', 'unknown')
                }
            )

def setup_cors_middleware(app, allowed_origins: list[str]):
    """CORS 미들웨어 설정"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
    )

def setup_all_middlewares(app, settings):
    """모든 미들웨어 설정"""
    # 주의: 미들웨어는 나중에 등록된 것부터 먼저 실행됨
    
    # 1. CORS (가장 먼저 실행되어야 함)
    setup_cors_middleware(app, settings.allowed_origins_list)
    
    # 2. 보안 헤더
    app.add_middleware(SecurityHeadersMiddleware)
    
    # 3. Rate Limiting
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.RATE_LIMIT_REQUESTS,
        period=settings.RATE_LIMIT_PERIOD
    )
    
    # 4. 로깅 (가장 안쪽에서 로깅)
    app.add_middleware(LoggingMiddleware)
    
    # 5. 에러 핸들링 (가장 바깥쪽에서 에러 캐치)
    app.add_middleware(ErrorHandlingMiddleware)
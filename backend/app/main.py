"""
FastAPI application entry point for TradingAgentsX Backend
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import sys
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

from backend.app.core.config import settings
from backend.app.core.cors import setup_cors
from backend.app.api.routes import router
from backend.app.api.auth import router as auth_router
from backend.app.api.user import router as user_router

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware"""
    
    def __init__(self, app, max_requests: int = 30, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path == "/api/health":
            return await call_next(request)
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        
        # Clean old requests
        now = time.time()
        cutoff = now - self.window_seconds
        self.requests[client_ip] = [
            t for t in self.requests[client_ip] if t > cutoff
        ]
        
        # Check rate limit
        if len(self.requests[client_ip]) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - self.requests[client_ip][0]))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "message": f"Rate limit exceeded. Please wait {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        
        # Record this request
        self.requests[client_ip].append(now)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = self.max_requests - len(self.requests[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(now + self.window_seconds))
        
        return response


class SensitiveDataFilter(logging.Filter):
    """Filter to mask API keys in log messages"""
    
    SENSITIVE_PATTERNS = ["api_key", "apikey", "api-key", "token", "secret", "password"]
    
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            msg = record.msg
            for pattern in self.SENSITIVE_PATTERNS:
                if pattern.lower() in msg.lower():
                    # Mask the value after the pattern
                    import re
                    msg = re.sub(
                        rf'({pattern}["\']?\s*[=:]\s*["\']?)([^"\'\s,}}]+)',
                        r'\1**********',
                        msg,
                        flags=re.IGNORECASE
                    )
            record.msg = msg
        return True


# Add sensitive data filter to all loggers
for handler in logging.root.handlers:
    handler.addFilter(SensitiveDataFilter())


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Multi-Agent LLM Financial Trading Framework - REST API",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add security middleware (order matters - added first, executed last)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=30, window_seconds=60)

# Setup CORS
setup_cors(app)

# Include API routes
app.include_router(router)
app.include_router(auth_router)
app.include_router(user_router)


# Database initialization on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    try:
        from backend.app.db import init_db, check_db_connection
        
        # Check if database is configured
        if await check_db_connection():
            logger.info("Database connection successful")
            await init_db()
            logger.info("Database tables initialized")
        else:
            logger.warning("Database not configured or connection failed - running without database")
    except Exception as e:
        logger.warning(f"Database initialization failed: {e} - running without database")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to TradingAgentsX API",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler - masks sensitive data in errors"""
    error_msg = str(exc)
    
    # Mask any API keys that might be in the error message
    import re
    patterns = ["sk-", "sk-ant-", "xai-", "AIza"]
    for pattern in patterns:
        error_msg = re.sub(
            rf'{pattern}[a-zA-Z0-9_-]+',
            f'{pattern}**********',
            error_msg
        )
    
    logger.error(f"Unhandled exception: {error_msg}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": error_msg,
            "type": type(exc).__name__,
        },
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info" if settings.debug else "warning",
    )

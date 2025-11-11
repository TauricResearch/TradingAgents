# Security Standards - TradingAgents

## API Key Management

### OpenRouter and LLM Provider Security

**Environment Variable Management**:
```bash
# Required API keys
export OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxx"

# Optional provider keys (for fallback)
export OPENAI_API_KEY="sk-xxxxxxxxxxxx"
export ANTHROPIC_API_KEY="sk-ant-xxxxxxxxxxxx"

# Financial data APIs
export FINNHUB_API_KEY="xxxxxxxxxxxx"
export ALPHA_VANTAGE_API_KEY="xxxxxxxxxxxx"
```

**Configuration Security**:
```python
import os
from pathlib import Path

class SecureConfig:
    """Secure configuration management with validation"""
    
    @classmethod
    def get_required_env(cls, key: str, description: str = "") -> str:
        """Get required environment variable with validation"""
        value = os.getenv(key)
        if not value:
            raise EnvironmentError(
                f"Required environment variable {key} not set. {description}"
            )
        
        # Validate API key format
        if key.endswith("_API_KEY"):
            cls._validate_api_key(key, value)
        
        return value
    
    @classmethod
    def _validate_api_key(cls, key: str, value: str) -> None:
        """Validate API key format and warn on potential issues"""
        if len(value) < 20:
            raise ValueError(f"API key {key} appears too short (< 20 chars)")
        
        if value.startswith("sk-") and len(value) < 40:
            raise ValueError(f"OpenAI/OpenRouter API key {key} appears invalid")
        
        # Detect placeholder values
        placeholder_patterns = ["your_", "replace_", "xxxx", "test"]
        if any(pattern in value.lower() for pattern in placeholder_patterns):
            raise ValueError(f"API key {key} appears to be a placeholder")
    
    @classmethod
    def load_openrouter_config(cls) -> dict[str, str]:
        """Load and validate OpenRouter configuration"""
        return {
            "api_key": cls.get_required_env(
                "OPENROUTER_API_KEY", 
                "Get your key from https://openrouter.ai/keys"
            ),
            "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "app_name": os.getenv("OPENROUTER_APP_NAME", "TradingAgents"),
            "site_url": os.getenv("OPENROUTER_SITE_URL", "https://github.com/TauricResearch/TradingAgents")
        }
```

**Development vs Production Key Management**:
```python
# .env.example (committed to repo)
OPENROUTER_API_KEY=your_openrouter_api_key_here
DATABASE_URL=postgresql+asyncpg://postgres:tradingagents@localhost:5432/tradingagents
TRADINGAGENTS_RESULTS_DIR=./results
TRADINGAGENTS_DATA_DIR=./data

# .env (never committed, gitignored)
OPENROUTER_API_KEY=sk-or-v1-actual-key-here
DATABASE_URL=postgresql+asyncpg://user:password@prod-db:5432/tradingagents
```

### Secret Rotation and Management

**Key Rotation Strategy**:
```python
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class APIKeyManager:
    """Manages API key rotation and health monitoring"""
    
    def __init__(self):
        self.key_health: Dict[str, Dict] = {}
        self.rotation_schedule: Dict[str, datetime] = {}
    
    async def validate_key_health(self, service: str, api_key: str) -> bool:
        """Test API key validity with minimal request"""
        try:
            if service == "openrouter":
                return await self._test_openrouter_key(api_key)
            elif service == "finnhub":
                return await self._test_finnhub_key(api_key)
            else:
                logger.warning(f"No health check implemented for {service}")
                return True
        except Exception as e:
            logger.error(f"API key health check failed for {service}: {e}")
            return False
    
    async def _test_openrouter_key(self, api_key: str) -> bool:
        """Test OpenRouter key with lightweight request"""
        import aiohttp
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Use minimal model list request to test auth
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://openrouter.ai/api/v1/models",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                return response.status == 200
    
    def schedule_rotation(self, service: str, days: int = 90) -> None:
        """Schedule API key rotation"""
        rotation_date = datetime.now() + timedelta(days=days)
        self.rotation_schedule[service] = rotation_date
        logger.info(f"Scheduled {service} key rotation for {rotation_date.date()}")
    
    def get_rotation_alerts(self) -> list[str]:
        """Get list of keys requiring rotation"""
        alerts = []
        now = datetime.now()
        warning_threshold = timedelta(days=7)
        
        for service, rotation_date in self.rotation_schedule.items():
            if now >= rotation_date:
                alerts.append(f"URGENT: {service} API key rotation overdue")
            elif now >= rotation_date - warning_threshold:
                alerts.append(f"WARNING: {service} API key rotation due in {(rotation_date - now).days} days")
        
        return alerts
```

## Database Security Patterns

### Connection Security

**Secure Connection Configuration**:
```python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
import ssl

class SecureDatabaseManager:
    """Database manager with security-first configuration"""
    
    def __init__(self, database_url: str, require_ssl: bool = True):
        # Parse and validate database URL
        if not database_url.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("Only PostgreSQL databases are supported")
        
        # Ensure asyncpg driver for better async performance
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
        
        # SSL/TLS configuration for production
        connect_args = {}
        if require_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False  # Often needed for cloud databases
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            connect_args["ssl"] = ssl_context
        
        self.engine = create_async_engine(
            database_url,
            # Security settings
            connect_args=connect_args,
            pool_pre_ping=True,                  # Verify connections
            pool_recycle=3600,                   # Recycle connections (1 hour)
            
            # Connection limits to prevent resource exhaustion
            pool_size=10,                        # Base connection pool
            max_overflow=20,                     # Additional connections under load
            
            # Prevent connection leaks in development
            poolclass=NullPool if self._is_test_env() else None,
            
            # Disable SQL echo in production (information disclosure)
            echo=False if os.getenv("ENVIRONMENT") == "production" else False
        )
    
    def _is_test_env(self) -> bool:
        """Detect test environment"""
        return any([
            "test" in os.getenv("DATABASE_URL", "").lower(),
            os.getenv("TESTING") == "true",
            "pytest" in sys.modules
        ])
    
    async def create_tables_secure(self):
        """Create tables with security considerations"""
        async with self.engine.begin() as conn:
            # Set secure session parameters
            await conn.execute(text("SET session_replication_role = 'origin'"))
            await conn.execute(text("SET log_statement = 'none'"))  # Disable query logging for DDL
            
            # Create tables
            await conn.run_sync(Base.metadata.create_all)
            
            # Set up row-level security policies if needed
            await self._setup_row_level_security(conn)
    
    async def _setup_row_level_security(self, conn):
        """Configure row-level security for multi-tenant data"""
        # Enable RLS on sensitive tables
        await conn.execute(text("ALTER TABLE news_articles ENABLE ROW LEVEL SECURITY"))
        
        # Create policy for data isolation (if implementing multi-user features)
        # await conn.execute(text("""
        #     CREATE POLICY user_data_policy ON news_articles
        #     FOR ALL TO app_user
        #     USING (user_id = current_setting('app.user_id')::UUID)
        # """))
```

### Data Privacy and Anonymization

**Financial Data Protection**:
```python
import hashlib
import secrets
from typing import Any, Dict

class DataPrivacyManager:
    """Handles sensitive financial data with privacy controls"""
    
    def __init__(self):
        self.salt = self._get_or_create_salt()
    
    def _get_or_create_salt(self) -> bytes:
        """Get encryption salt from secure storage"""
        salt_path = Path(os.getenv("TRADINGAGENTS_DATA_DIR", "./data")) / ".salt"
        
        if salt_path.exists():
            return salt_path.read_bytes()
        else:
            # Generate cryptographically secure salt
            salt = secrets.token_bytes(32)
            salt_path.write_bytes(salt)
            salt_path.chmod(0o600)  # Restrict file permissions
            return salt
    
    def hash_symbol(self, symbol: str) -> str:
        """Create consistent hash for symbols (for analytics without exposure)"""
        return hashlib.pbkdf2_hmac(
            'sha256',
            symbol.encode(),
            self.salt,
            100000  # iterations
        ).hex()[:16]
    
    def sanitize_article_content(self, content: str) -> str:
        """Remove PII and sensitive information from article content"""
        import re
        
        # Remove potential SSNs, account numbers, etc.
        patterns = [
            r'\b\d{3}-\d{2}-\d{4}\b',      # SSN
            r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',  # Credit card
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        ]
        
        sanitized = content
        for pattern in patterns:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized)
        
        return sanitized
    
    def audit_data_access(self, table: str, operation: str, record_count: int = 1):
        """Log data access for compliance auditing"""
        logger.info(
            "Data access audit",
            extra={
                "table": table,
                "operation": operation,
                "record_count": record_count,
                "timestamp": datetime.utcnow().isoformat(),
                "user": os.getenv("USER", "system")
            }
        )
```

### Query Security

**SQL Injection Prevention**:
```python
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

class SecureQueryBuilder:
    """Build secure parameterized queries"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_articles_secure(
        self, 
        symbol: str, 
        date_filter: date,
        user_input_query: Optional[str] = None
    ) -> list[NewsArticle]:
        """Secure article query with parameterization"""
        
        # Base query with parameterized symbol and date
        query = select(NewsArticleEntity).where(
            and_(
                NewsArticleEntity.symbol == symbol,  # Parameterized automatically
                NewsArticleEntity.published_date == date_filter
            )
        )
        
        # Secure text search if provided
        if user_input_query:
            # Use full-text search instead of LIKE to prevent injection
            # Sanitize and escape the search term
            sanitized_query = self._sanitize_search_term(user_input_query)
            query = query.where(
                NewsArticleEntity.headline.match(sanitized_query)  # PostgreSQL full-text search
            )
        
        result = await self.session.execute(query)
        return [NewsArticle.from_entity(e) for e in result.scalars()]
    
    def _sanitize_search_term(self, query: str) -> str:
        """Sanitize user input for full-text search"""
        import re
        
        # Remove SQL injection patterns
        dangerous_patterns = [
            r"[';\"\\]",           # SQL metacharacters
            r"\b(union|select|drop|delete|update|insert)\b",  # SQL keywords
            r"--",                 # SQL comments
            r"/\*.*?\*/"          # SQL block comments
        ]
        
        sanitized = query
        for pattern in dangerous_patterns:
            sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
        
        # Limit length to prevent DoS
        sanitized = sanitized[:100]
        
        # Convert to PostgreSQL full-text search format
        terms = sanitized.split()
        return " & ".join(f'"{term}"' for term in terms if term.isalnum())
    
    async def execute_safe_raw_query(self, query_template: str, **params) -> Any:
        """Execute raw SQL with parameter validation"""
        # Whitelist allowed query templates
        allowed_templates = {
            "performance_stats": "SELECT * FROM pg_stat_statements WHERE query LIKE :pattern",
            "table_sizes": "SELECT schemaname, tablename, pg_total_relation_size(schemaname||'.'||tablename) as size FROM pg_tables WHERE schemaname = :schema"
        }
        
        if query_template not in allowed_templates:
            raise ValueError(f"Query template not in whitelist: {query_template}")
        
        # Validate parameters
        for key, value in params.items():
            if not self._validate_parameter(key, value):
                raise ValueError(f"Invalid parameter {key}: {value}")
        
        query = text(allowed_templates[query_template])
        result = await self.session.execute(query, params)
        return result.fetchall()
    
    def _validate_parameter(self, key: str, value: Any) -> bool:
        """Validate query parameters"""
        # Length limits
        if isinstance(value, str) and len(value) > 100:
            return False
        
        # Type restrictions
        if key.endswith("_id") and not isinstance(value, (str, int)):
            return False
        
        # No SQL injection patterns
        if isinstance(value, str):
            dangerous = ["'", '"', ";", "--", "/*", "*/", "union", "select"]
            if any(pattern in value.lower() for pattern in dangerous):
                return False
        
        return True
```

## Development Environment Security

### Local Development Protection

**Secure Development Setup**:
```bash
#!/bin/bash
# secure_dev_setup.sh - Secure development environment initialization

set -euo pipefail

# 1. Create secure data directory
DATA_DIR="${TRADINGAGENTS_DATA_DIR:-./data}"
mkdir -p "$DATA_DIR"
chmod 700 "$DATA_DIR"  # Owner read/write/execute only

# 2. Create .env file with secure permissions
if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env  # Owner read/write only
    echo "Created .env file. Please update with actual API keys."
fi

# 3. Set up secure Docker environment
if [ ! -f docker-compose.override.yml ]; then
    cat > docker-compose.override.yml << EOF
version: '3.8'
services:
  timescaledb:
    environment:
      # Use strong password in development
      POSTGRES_PASSWORD: \${DB_PASSWORD:-$(openssl rand -base64 32)}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
EOF
    echo "Created docker-compose.override.yml with secure settings"
fi

# 4. Configure Git security
git config --local core.hooksPath .githooks
chmod +x .githooks/pre-commit

# 5. Install security scanning tools
if command -v pip &> /dev/null; then
    pip install bandit safety
    echo "Installed security scanning tools"
fi

echo "Secure development environment configured"
echo "Remember to:"
echo "  1. Update .env with real API keys"
echo "  2. Never commit .env or API keys"
echo "  3. Run 'bandit -r tradingagents/' before commits"
```

**Git Security Hooks**:
```bash
#!/bin/bash
# .githooks/pre-commit - Prevent secrets from being committed

# Check for common secret patterns
if git diff --cached --name-only | grep -E "\.(py|yml|yaml|json|env)$"; then
    echo "Scanning for secrets..."
    
    # Pattern matching for common secrets
    if git diff --cached | grep -i -E "(api_key|secret|password|token)" | grep -v -E "(example|template|your_|replace_)"; then
        echo "ERROR: Potential secrets detected in staged files!"
        echo "Please review and remove any sensitive information."
        exit 1
    fi
    
    # Check for hardcoded URLs with credentials
    if git diff --cached | grep -E "postgresql://[^:]+:[^@]+@"; then
        echo "ERROR: Database URL with credentials detected!"
        echo "Use environment variables instead."
        exit 1
    fi
fi

# Run security linting if bandit is available
if command -v bandit &> /dev/null; then
    echo "Running security scan..."
    bandit -r tradingagents/ -f json | jq '.results[] | select(.issue_severity == "HIGH")' | grep -q . && {
        echo "ERROR: High-severity security issues found!"
        echo "Run 'bandit -r tradingagents/' for details."
        exit 1
    }
fi

echo "Pre-commit security checks passed"
```

### Secrets Management with Environment Variables

**Environment Variable Security**:
```python
import os
from pathlib import Path
from typing import Optional

class EnvironmentManager:
    """Secure environment variable management"""
    
    def __init__(self):
        self.env_file = Path(".env")
        self.required_vars = [
            "OPENROUTER_API_KEY",
            "DATABASE_URL"
        ]
        self.sensitive_vars = [
            "API_KEY", "SECRET", "PASSWORD", "TOKEN", "PRIVATE_KEY"
        ]
    
    def validate_environment(self) -> list[str]:
        """Validate environment setup and return any issues"""
        issues = []
        
        # Check required variables
        for var in self.required_vars:
            if not os.getenv(var):
                issues.append(f"Missing required environment variable: {var}")
        
        # Check .env file permissions
        if self.env_file.exists():
            stat = self.env_file.stat()
            if stat.st_mode & 0o077:  # Check if group/other have any permissions
                issues.append(".env file has overly permissive permissions (should be 600)")
        
        # Validate sensitive variables aren't using placeholder values
        for var_name in os.environ:
            if any(sensitive in var_name for sensitive in self.sensitive_vars):
                value = os.getenv(var_name, "")
                if self._is_placeholder_value(value):
                    issues.append(f"{var_name} appears to contain a placeholder value")
        
        return issues
    
    def _is_placeholder_value(self, value: str) -> bool:
        """Detect common placeholder patterns"""
        placeholders = [
            "your_", "replace_", "change_me", "xxxx", "test_key",
            "example", "sample", "placeholder", "todo"
        ]
        return any(placeholder in value.lower() for placeholder in placeholders)
    
    def setup_production_env(self) -> dict[str, str]:
        """Configure production environment with security hardening"""
        return {
            # Security settings
            "PYTHONDONTWRITEBYTECODE": "1",     # Don't create .pyc files
            "PYTHONUNBUFFERED": "1",           # Unbuffered output
            "PYTHONHASHSEED": "random",        # Random hash seed
            
            # Application security
            "ENVIRONMENT": "production",
            "DEBUG": "false",
            "LOG_LEVEL": "INFO",               # Don't log debug info
            
            # Database security
            "DB_SSL_MODE": "require",
            "DB_POOL_PRE_PING": "true",
            "DB_ECHO": "false",                # Don't log SQL queries
            
            # API security
            "API_RATE_LIMIT": "100",           # Requests per minute
            "API_TIMEOUT": "30",               # Request timeout in seconds
        }

def main():
    """Development environment security check"""
    env_manager = EnvironmentManager()
    issues = env_manager.validate_environment()
    
    if issues:
        print("⚠️  Environment Security Issues:")
        for issue in issues:
            print(f"  - {issue}")
        print("\nRun ./scripts/secure_dev_setup.sh to fix common issues")
        return 1
    else:
        print("✅ Environment security validation passed")
        return 0

if __name__ == "__main__":
    exit(main())
```

## Production Security Considerations

### API Rate Limiting and DoS Protection

**Request Throttling**:
```python
import asyncio
import time
from collections import defaultdict
from typing import Dict, Optional

class RateLimiter:
    """Protect against API abuse and DoS attacks"""
    
    def __init__(self):
        self.request_counts: Dict[str, list] = defaultdict(list)
        self.blocked_ips: Dict[str, float] = {}
        self.rate_limits = {
            "default": (100, 60),      # 100 requests per 60 seconds
            "openrouter": (50, 60),    # 50 LLM requests per 60 seconds  
            "database": (1000, 60),    # 1000 DB operations per 60 seconds
        }
    
    async def check_rate_limit(
        self, 
        identifier: str, 
        category: str = "default"
    ) -> tuple[bool, Optional[str]]:
        """Check if request should be allowed"""
        
        # Check if identifier is temporarily blocked
        if identifier in self.blocked_ips:
            block_until = self.blocked_ips[identifier]
            if time.time() < block_until:
                return False, f"Temporarily blocked until {time.ctime(block_until)}"
            else:
                del self.blocked_ips[identifier]
        
        # Get rate limit for category
        max_requests, window_seconds = self.rate_limits.get(
            category, self.rate_limits["default"]
        )
        
        # Clean old requests outside window
        now = time.time()
        cutoff = now - window_seconds
        self.request_counts[identifier] = [
            req_time for req_time in self.request_counts[identifier]
            if req_time > cutoff
        ]
        
        # Check if within limits
        current_count = len(self.request_counts[identifier])
        if current_count >= max_requests:
            # Block for increasing duration based on violations
            violation_count = getattr(self, f"_{identifier}_violations", 0) + 1
            setattr(self, f"_{identifier}_violations", violation_count)
            
            block_duration = min(300, 30 * violation_count)  # Max 5 minutes
            self.blocked_ips[identifier] = now + block_duration
            
            return False, f"Rate limit exceeded. Blocked for {block_duration} seconds"
        
        # Record this request
        self.request_counts[identifier].append(now)
        return True, None
    
    async def check_api_health(self) -> dict:
        """Monitor for suspicious patterns"""
        now = time.time()
        
        # Count recent requests across all identifiers
        recent_requests = 0
        for requests in self.request_counts.values():
            recent_requests += len([r for r in requests if r > now - 60])
        
        # Calculate metrics
        total_blocked = len(self.blocked_ips)
        active_identifiers = len([
            requests for requests in self.request_counts.values()
            if any(r > now - 300 for r in requests)  # Active in last 5 minutes
        ])
        
        status = "healthy"
        if recent_requests > 500:  # Threshold for concern
            status = "high_load"
        if total_blocked > 10:
            status = "under_attack"
        
        return {
            "status": status,
            "recent_requests_per_minute": recent_requests,
            "blocked_identifiers": total_blocked,
            "active_identifiers": active_identifiers,
            "timestamp": now
        }
```

### Audit Logging and Compliance

**Security Event Logging**:
```python
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

class SecurityEventType(Enum):
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    DATA_ACCESS = "data_access"
    DATA_EXPORT = "data_export"
    CONFIG_CHANGE = "config_change"
    API_ABUSE = "api_abuse"
    SYSTEM_ERROR = "system_error"

class SecurityAuditor:
    """Centralized security event logging for compliance"""
    
    def __init__(self):
        # Separate logger for security events
        self.security_logger = logging.getLogger("tradingagents.security")
        
        # Configure structured logging handler
        handler = logging.FileHandler("logs/security.log")
        formatter = SecurityLogFormatter()
        handler.setFormatter(formatter)
        self.security_logger.addHandler(handler)
        self.security_logger.setLevel(logging.INFO)
    
    def log_event(
        self,
        event_type: SecurityEventType,
        message: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log security event with structured data"""
        
        event_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type.value,
            "message": message,
            "severity": self._get_severity(event_type),
            "user_id": user_id or "system",
            "ip_address": ip_address or "unknown",
            "resource": resource,
            "additional_data": additional_data or {},
            "process_id": os.getpid(),
            "hostname": os.uname().nodename
        }
        
        # Log at appropriate level based on severity
        if event_data["severity"] == "critical":
            self.security_logger.critical(json.dumps(event_data))
        elif event_data["severity"] == "warning":
            self.security_logger.warning(json.dumps(event_data))
        else:
            self.security_logger.info(json.dumps(event_data))
    
    def _get_severity(self, event_type: SecurityEventType) -> str:
        """Determine event severity"""
        critical_events = {
            SecurityEventType.AUTH_FAILURE,
            SecurityEventType.API_ABUSE,
            SecurityEventType.CONFIG_CHANGE
        }
        
        if event_type in critical_events:
            return "critical"
        elif event_type == SecurityEventType.SYSTEM_ERROR:
            return "warning"
        else:
            return "info"
    
    def log_data_access(
        self,
        table: str,
        operation: str,
        record_count: int,
        user_id: str = "system"
    ) -> None:
        """Log data access for compliance auditing"""
        self.log_event(
            SecurityEventType.DATA_ACCESS,
            f"Database {operation} on {table}",
            user_id=user_id,
            resource=table,
            additional_data={
                "operation": operation,
                "record_count": record_count
            }
        )
    
    def log_api_key_usage(
        self,
        provider: str,
        model: str,
        tokens_used: int,
        cost_estimate: float
    ) -> None:
        """Log LLM API usage for cost monitoring and abuse detection"""
        self.log_event(
            SecurityEventType.DATA_ACCESS,
            f"LLM API call to {provider}/{model}",
            resource=f"{provider}/{model}",
            additional_data={
                "tokens_used": tokens_used,
                "cost_estimate": cost_estimate,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

class SecurityLogFormatter(logging.Formatter):
    """Custom formatter for security logs"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Security logs are already JSON formatted
        return record.getMessage()

# Usage in repository classes
class NewsRepository:
    def __init__(self, database_manager: DatabaseManager):
        self.db_manager = database_manager
        self.auditor = SecurityAuditor()
    
    async def list(self, symbol: str, date: date) -> list[NewsArticle]:
        # ... existing implementation ...
        
        # Log data access for compliance
        self.auditor.log_data_access(
            table="news_articles",
            operation="SELECT",
            record_count=len(result),
            user_id=getattr(self, 'current_user_id', 'system')
        )
        
        return result
```

This comprehensive security standards document provides the foundation for protecting sensitive financial data, API keys, and system resources while maintaining compliance with data protection regulations in the TradingAgents system.
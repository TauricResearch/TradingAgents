# PROJECT.md Structure Example

A well-structured PROJECT.md example demonstrating best practices for GOALS, SCOPE, CONSTRAINTS, and ARCHITECTURE sections.

---

# Example: SaaS Platform PROJECT.md

## PROJECT OVERVIEW

**Project Name**: TaskFlow - Team Task Management Platform

**Vision**: Enable remote teams to collaborate efficiently with intuitive task management and real-time communication.

**Phase**: MVP (Launch in Q1 2025)

**Last Updated**: 2024-11-16

---

## GOALS

Clear, measurable objectives that define project success.

### Primary Goals

**1. Launch Minimum Viable Product by March 31, 2025**
- **Metric**: Product live in production
- **Success Criteria**: Core features functional, minimal bugs
- **Why**: First-mover advantage in remote work tools market

**2. Validate Product-Market Fit**
- **Metric**: 100 active teams (500+ users) within 3 months of launch
- **Success Criteria**: 60% weekly active user rate, NPS > 40
- **Why**: Prove demand before scaling investment

**3. Achieve Technical Excellence**
- **Metric**: 80% test coverage, zero critical security vulnerabilities
- **Success Criteria**: Automated tests pass, security audit clean
- **Why**: Build foundation for reliable, secure platform

### Secondary Goals

**4. Keep Operating Costs Low**
- **Metric**: Infrastructure costs < $5,000/month
- **Success Criteria**: Serve 1,000 users within budget
- **Why**: Maintain runway until revenue starts

**5. Enable Fast Iteration**
- **Metric**: Deploy new features weekly
- **Success Criteria**: CI/CD pipeline < 10 minutes, zero downtime deploys
- **Why**: Respond quickly to user feedback

---

## SCOPE

### In Scope (MVP Features)

**Authentication & User Management**
- ✓ Email/password registration and login
- ✓ OAuth (Google, GitHub) for easy sign-in
- ✓ User profile management (name, email, avatar, password)
- ✓ Team creation and member invitations
- ✓ Role-based access control (Admin, Member, Viewer)

**Core Task Management**
- ✓ Create, edit, delete tasks
- ✓ Task assignment to team members
- ✓ Task status (To Do, In Progress, Done)
- ✓ Task priority (High, Medium, Low)
- ✓ Due dates and reminders
- ✓ Task comments and activity log
- ✓ File attachments (up to 10MB per file)

**Team Collaboration**
- ✓ Team workspaces with multiple projects
- ✓ Project boards (Kanban view)
- ✓ Real-time updates (WebSocket notifications)
- ✓ @mentions in comments
- ✓ Activity feed per project

**Basic Integrations**
- ✓ Email notifications for task assignments and mentions
- ✓ Slack webhook for team notifications
- ✓ Calendar export (iCal format)

**Admin Features**
- ✓ Team member management
- ✓ Usage dashboard (tasks created, users active)
- ✓ Audit log for team actions

---

### Out of Scope (Future Versions)

**Advanced Task Features** (v2.0 - Q2 2025)
- ✗ Recurring tasks
- ✗ Task dependencies and Gantt charts
- ✗ Time tracking and estimates
- ✗ Custom task fields
- ✗ Advanced filtering and saved views

**Enterprise Features** (v3.0 - Q3 2025)
- ✗ Single Sign-On (SAML)
- ✗ Advanced permissions and team hierarchies
- ✗ Custom branding and white-labeling
- ✗ SLA guarantees and dedicated support

**Advanced Integrations** (v2.0+)
- ✗ Two-way sync with Jira, Asana, Trello
- ✗ GitHub/GitLab issue sync
- ✗ Zapier integration
- ✗ Mobile apps (iOS, Android)

**Billing & Payments** (v2.0 - Q2 2025)
- ✗ Subscription management
- ✗ Payment processing
- ✗ Usage-based billing
- ✗ Invoicing

**AI Features** (v3.0+ - TBD)
- ✗ AI-powered task suggestions
- ✗ Automated task prioritization
- ✗ Natural language task creation

---

### Scope Boundaries

**What "Real-time updates" means in MVP**:
- ✓ Task status changes appear immediately for all team members
- ✓ New comments show up without refresh
- ✓ User presence indicators (who's online)
- ✗ NOT real-time collaborative editing of task descriptions
- ✗ NOT typing indicators in comments

**What "File attachments" means in MVP**:
- ✓ Upload files to tasks (images, PDFs, documents)
- ✓ Maximum 10MB per file, 100MB per team
- ✓ Virus scanning before storage
- ✗ NOT file versioning or history
- ✗ NOT online document editing
- ✗ NOT file previews (download to view)

**What "Integrations" means in MVP**:
- ✓ Outbound webhooks (we push to Slack)
- ✓ Email notifications (we send emails)
- ✗ NOT inbound integrations (other services push to us)
- ✗ NOT two-way sync with other platforms

---

## CONSTRAINTS

### Technical Constraints

**Technology Stack** (Required)
- **Language**: Python 3.11+ (type hints required, async support)
- **Web Framework**: FastAPI (chosen for async, auto-docs, performance)
- **Database**: PostgreSQL 14+ (JSONB for flexibility, CTEs for queries)
- **Cache/Queue**: Redis 7+ (session storage, WebSocket pub/sub, task queue)
- **Frontend**: React 18+ with TypeScript (type safety, component reuse)
- **Deployment**: Docker containers on AWS ECS (portability, scaling)

**Performance Requirements**
- API response time: < 200ms (P95) for read operations
- API response time: < 500ms (P95) for write operations
- Page load time: < 2 seconds (P95) on 3G connection
- WebSocket message delivery: < 100ms
- File upload: Support up to 10MB files
- Concurrent users: Handle 1,000 simultaneous users

**Security Requirements**
- OWASP Top 10 compliance (no critical vulnerabilities)
- All data encrypted in transit (TLS 1.3)
- Passwords hashed with bcrypt (cost factor 12)
- JWT tokens for authentication (15-minute expiry, refresh tokens)
- CSRF protection on all state-changing endpoints
- Rate limiting: 100 requests/minute per user
- Input validation: All user input sanitized (XSS, SQL injection prevention)
- File uploads: Virus scanning, type validation, size limits
- Audit logging: All sensitive actions logged (CWE-117 compliance)

**Scalability Requirements**
- Stateless API (can add servers horizontally)
- Database connection pooling (max 20 connections per instance)
- Redis for session storage (no in-memory sessions)
- CDN for static assets (CloudFront)
- Graceful degradation if WebSocket unavailable (fallback to polling)

**Code Quality Requirements**
- Test coverage: 80% minimum (unit + integration tests)
- Type hints: Required for all public APIs
- Linting: Black, isort, mypy, ESLint pass
- Code review: Required for all changes (2 approvals for core changes)
- Documentation: Docstrings for all public functions/classes

---

### Resource Constraints

**Budget**
- Infrastructure: < $5,000/month (AWS, Redis, CDN, email service)
- Development tools: < $500/month (GitHub, monitoring, CI/CD)
- Total: < $5,500/month until revenue starts

**Timeline**
- MVP launch: March 31, 2025 (16 weeks from project start)
- Beta testing: 2 weeks before launch (March 17-31)
- Feature freeze: March 10 (3 weeks before launch)
- No major scope changes after January 31

**Team Capacity**
- 2 full-time developers (backend + frontend)
- 1 part-time designer (UI/UX)
- 1 product owner (stakeholder decisions)
- No dedicated QA (developers own testing)
- No ML/AI expertise (defer AI features)

---

### Policy Constraints

**Compliance**
- GDPR compliant (EU users must be able to export/delete data)
- Data residency: US and EU regions only (no data in other countries)
- Privacy policy required before collecting user data
- Terms of service required before launch

**Licensing**
- MIT/Apache 2.0 dependencies only (no GPL, no AGPL)
- All code owned by company (no copyleft issues)
- Third-party services: Must have commercial license or free tier

**Business Rules**
- Free tier during beta (no payment processing)
- Email opt-in required for marketing (GDPR, CAN-SPAM)
- No selling user data (privacy commitment)

---

## ARCHITECTURE

### High-Level Architecture

**Three-Tier Architecture**
```
┌─────────────────┐
│   React SPA     │  (Frontend - TypeScript, React 18)
│   (CloudFront)  │  - Component-based UI
└────────┬────────┘  - State management (Redux)
         │ HTTPS     - WebSocket client
         ▼
┌─────────────────┐
│   FastAPI       │  (Backend - Python 3.11, FastAPI)
│   (ECS)         │  - RESTful API
└────────┬────────┘  - WebSocket server
         │           - Business logic
         ▼
┌─────────────────┐
│   PostgreSQL    │  (Database - RDS)
│   Redis         │  (Cache, Queue, Pub/Sub)
└─────────────────┘
```

---

### Design Principles

**1. API-First Design**
- Backend exposes RESTful API
- Frontend consumes API (decoupled from backend)
- API documented with OpenAPI/Swagger (auto-generated)
- Versioning: `/api/v1/` prefix for breaking changes

**2. Stateless Services**
- No in-memory session storage (use Redis)
- JWT tokens for authentication (stateless)
- API servers can be added/removed without data loss
- Horizontal scaling via load balancer

**3. Real-Time Communication**
- WebSocket for live updates (task changes, comments, presence)
- Redis pub/sub for broadcasting to multiple servers
- Fallback to polling if WebSocket unavailable (firewall, old browsers)
- Graceful degradation (app works without real-time)

**4. Security-First**
- All user input validated and sanitized
- Parameterized queries (no SQL injection)
- CSRF tokens on all mutations
- Rate limiting to prevent abuse
- Audit logging for sensitive actions (user deletion, permission changes)
- Regular security audits and dependency updates

**5. Progressive Enhancement**
- Core functionality works without JavaScript (forms submit)
- Enhanced UX with JavaScript enabled (real-time, no page refresh)
- Mobile-responsive (works on all screen sizes)

**6. Test-Driven Development**
- Write tests before implementation
- Unit tests for business logic (pytest)
- Integration tests for API endpoints
- E2E tests for critical user flows (Playwright)
- Automated tests run on every commit (CI/CD)

---

### Component Architecture

**Backend Components**

**API Layer** (`src/api/`)
- FastAPI routers for endpoints
- Request validation with Pydantic models
- Response serialization
- Error handling middleware

**Business Logic** (`src/services/`)
- Task service (create, update, delete, query)
- User service (authentication, profile management)
- Team service (team management, permissions)
- Notification service (email, WebSocket)

**Data Access** (`src/repositories/`)
- PostgreSQL repositories (SQLAlchemy ORM)
- Redis repositories (caching, sessions, pub/sub)
- Repository pattern (abstraction over data store)

**Authentication** (`src/auth/`)
- JWT token generation and validation
- OAuth integration (Google, GitHub)
- Password hashing (bcrypt)
- Session management (Redis)

**WebSocket** (`src/websocket/`)
- WebSocket connection management
- Redis pub/sub for broadcasting
- Presence tracking (who's online)
- Real-time event distribution

**Background Tasks** (`src/tasks/`)
- Email sending (queued via Redis)
- File processing (virus scan, optimization)
- Cleanup jobs (expired sessions, old notifications)

---

**Frontend Components**

**Pages** (`src/pages/`)
- Login/Signup
- Dashboard (project list, activity feed)
- Project Board (Kanban view)
- Task Detail
- Settings (profile, team management)

**Components** (`src/components/`)
- TaskCard (reusable task display)
- CommentThread (comments and activity)
- MemberList (team member avatars)
- Notifications (real-time notification bell)

**State Management** (`src/store/`)
- Redux store for global state
- Slices: tasks, projects, users, notifications
- Async actions for API calls
- WebSocket event handlers update store

**API Client** (`src/api/`)
- Axios wrapper for REST API calls
- WebSocket client for real-time updates
- Error handling and retry logic
- Authentication token management

---

### Data Architecture

**PostgreSQL Schema**

**Core Tables**:
- `users` - User accounts, authentication
- `teams` - Team workspaces
- `team_members` - Many-to-many (users ↔ teams) with roles
- `projects` - Projects within teams
- `tasks` - Tasks within projects
- `comments` - Comments on tasks
- `attachments` - File metadata (S3 storage)
- `audit_log` - Security-sensitive actions

**Indexes**:
- `tasks.project_id` - Fast project task lookup
- `tasks.assignee_id` - Fast user task lookup
- `tasks.status, tasks.priority` - Fast filtering
- `comments.task_id` - Fast comment lookup

**JSONB Fields** (Flexibility):
- `tasks.metadata` - Custom fields (future extensibility)
- `users.preferences` - User settings

---

**Redis Data Structures**

**Session Storage**:
- Key: `session:{session_id}`
- Value: JSON (user_id, team_id, expiry)
- TTL: 7 days

**WebSocket Pub/Sub**:
- Channel: `team:{team_id}:updates`
- Message: JSON (event_type, task_id, changes)

**Rate Limiting**:
- Key: `ratelimit:{user_id}:{minute}`
- Value: Counter
- TTL: 60 seconds

**Cache**:
- Key: `cache:project:{project_id}:tasks`
- Value: JSON (task list)
- TTL: 5 minutes

---

### Deployment Architecture

**Production Environment**

**AWS Infrastructure**:
- **ECS Fargate**: API servers (auto-scaling 2-10 instances)
- **RDS PostgreSQL**: Database (Multi-AZ for HA)
- **ElastiCache Redis**: Cache and pub/sub (cluster mode)
- **S3**: File storage (attachments)
- **CloudFront**: CDN for frontend assets
- **Route 53**: DNS management
- **ALB**: Load balancer (TLS termination)

**CI/CD Pipeline**:
- GitHub Actions for automated testing
- Docker build and push to ECR
- ECS rolling deployment (zero downtime)
- Automated rollback on health check failure

**Monitoring**:
- CloudWatch for metrics (CPU, memory, request count)
- Application logs to CloudWatch Logs
- Error tracking with Sentry
- Uptime monitoring with UptimeRobot
- Alerts via PagerDuty (P1: < 5 min response)

**Backup Strategy**:
- PostgreSQL: Automated daily backups (7-day retention)
- S3: Versioning enabled (file recovery)
- Redis: AOF persistence (crash recovery)

---

### Security Architecture

**Authentication Flow**:
1. User submits credentials
2. Backend validates (bcrypt hash comparison)
3. Generate JWT access token (15 min expiry)
4. Generate refresh token (7 day expiry, stored in Redis)
5. Return both tokens to client
6. Client stores in httpOnly cookies (XSS protection)
7. API requests include access token
8. Token refresh on expiry

**Authorization Model**:
- Role-Based Access Control (RBAC)
- Roles: Admin (full access), Member (create/edit own tasks), Viewer (read-only)
- Team-level permissions (user can be Admin in one team, Member in another)
- Resource-level checks (can only edit tasks in teams you belong to)

**Data Protection**:
- TLS 1.3 for all traffic (no HTTP)
- Database encryption at rest (RDS encryption)
- S3 encryption at rest (AES-256)
- Password hashing (bcrypt, cost factor 12)
- JWT signing (HS256, secret rotation every 90 days)
- PII data: Encrypted in database (name, email)

**Audit Logging**:
- Log all security-sensitive actions
- Format: JSON (timestamp, user_id, action, resource, IP)
- Storage: CloudWatch Logs (immutable, 1-year retention)
- Monitored for suspicious patterns

---

### Error Handling

**API Error Responses**:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Task title is required",
    "details": {
      "field": "title",
      "constraint": "required"
    }
  }
}
```

**Error Codes**:
- `VALIDATION_ERROR` - Invalid input (400)
- `UNAUTHORIZED` - Authentication required (401)
- `FORBIDDEN` - Permission denied (403)
- `NOT_FOUND` - Resource doesn't exist (404)
- `RATE_LIMITED` - Too many requests (429)
- `INTERNAL_ERROR` - Server error (500)

**Error Handling Strategy**:
- Validation errors: Return helpful messages
- Server errors: Log details, return generic message
- Rate limit errors: Include retry-after header
- Network errors: Retry with exponential backoff (client)

---

### Performance Optimization

**Caching Strategy**:
- Page-level: CloudFront for static assets (1 day TTL)
- API-level: Redis for frequently accessed data (5 min TTL)
- Database: Query result caching (invalidate on write)

**Database Optimization**:
- Connection pooling (max 20 connections per API server)
- Read replicas for reporting queries (future)
- Indexed columns for common queries
- EXPLAIN ANALYZE for slow queries

**API Optimization**:
- Pagination for list endpoints (max 100 items per page)
- Field selection (client specifies which fields to return)
- Bulk operations (create/update multiple tasks in one request)
- Async processing for slow operations (file processing)

---

### Observability

**Logging**:
- Application logs: Structured JSON to CloudWatch
- Access logs: ALB logs to S3
- Database logs: Slow queries to CloudWatch
- Log levels: ERROR, WARN, INFO, DEBUG

**Metrics**:
- Request count, latency (P50, P95, P99)
- Error rate, status codes
- Database connection pool usage
- Redis hit/miss ratio
- WebSocket connection count

**Tracing** (Future):
- Distributed tracing with AWS X-Ray
- Trace API requests through services
- Identify performance bottlenecks

---

## VALIDATION CHECKLIST

Use this checklist to validate features against this PROJECT.md:

### GOALS Validation
- [ ] Feature serves at least one primary goal
- [ ] Feature doesn't conflict with other goals
- [ ] Feature priority aligns with goal priority
- [ ] Success metrics defined and aligned

### SCOPE Validation
- [ ] Feature is explicitly in In Scope section
- [ ] Feature doesn't touch Out of Scope items
- [ ] Dependencies are all in scope
- [ ] Scope boundaries respected (e.g., "real-time" definition)

### CONSTRAINTS Validation
- [ ] Tech stack compliance (Python 3.11, FastAPI, PostgreSQL, Redis, React)
- [ ] Performance requirements met (< 200ms API, < 2s page load)
- [ ] Security requirements met (OWASP, encryption, audit logging)
- [ ] Budget within limits (< $5.5k/month)
- [ ] Timeline respected (MVP by March 31, 2025)
- [ ] Code quality standards met (80% coverage, type hints, linting)

### ARCHITECTURE Validation
- [ ] Follows three-tier architecture
- [ ] Adheres to design principles (API-first, stateless, security-first)
- [ ] Uses defined components (API, services, repositories)
- [ ] Database schema aligned
- [ ] Deployment strategy compatible (Docker, ECS)
- [ ] Error handling pattern followed
- [ ] Observability implemented (logs, metrics)

---

**End of Example PROJECT.md**

---

## Key Takeaways from This Example

### 1. Specificity Over Ambiguity
- ✓ Explicit metrics for goals ("100 active teams")
- ✓ Clear scope boundaries ("Real-time means X, not Y")
- ✓ Specific constraints ("< 200ms", "Python 3.11+")
- ✗ Avoid vague goals ("good performance", "secure")

### 2. Actionable and Measurable
- ✓ Goals have metrics and success criteria
- ✓ Constraints have numbers (80% coverage, < 200ms)
- ✓ Architecture has clear patterns to follow
- ✗ Avoid "best effort" or "as much as possible"

### 3. Living Document
- Updated date at top (2024-11-16)
- Version tracking for sections (v2.0, v3.0 scope)
- Rationale documented ("Why changed from SQLite to PostgreSQL")
- Evolution expected and documented

### 4. Validation-Friendly
- Checklist at end for quick validation
- Clear In/Out of scope sections
- Scope boundaries explicitly defined
- Easy to verify alignment

### 5. Context for Decisions
- Explains "why" not just "what"
- Trade-offs documented (e.g., WebSocket vs polling)
- Alternatives considered and rejected
- Helps future maintainers understand reasoning

---

**See Also**:
- `alignment-scenarios.md` - How to validate against this structure
- `misalignment-examples.md` - What happens with poor structure
- `../docs/alignment-checklist.md` - Systematic validation process

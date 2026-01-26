# Product Requirements Document: Scraping Infrastructure Modernization

**Version:** 1.0  
**Date:** January 26, 2026  
**Owner:** Sebastian Winkler  
**Status:** Draft for Review

---

## Executive Summary

### Purpose
Modernize the job scraping infrastructure to support scaling from 125 to 500-1,000 companies while maintaining reliability, data quality, and operational efficiency for a lifestyle business model (max 20h/week, €500k annual revenue target).

### Current State
- 125 companies scraped via Python scripts on Google Cloud Engine
- Mix of API JSON extraction and HTML parsing approaches
- GCS-based master list storage with race condition risks
- Hardcoded credentials and limited error handling
- Shell-based orchestration organized by industry

### Target State
- Unified, modular scraper architecture supporting multiple extraction methods
- Postgres-first data storage with GCS for BLOBs
- Production-grade error handling, monitoring, and recovery mechanisms
- Google Cloud Platform migration (Cloud Run Jobs, Cloud SQL, Cloud Scheduler)
- Infrastructure capable of handling 500-1,000 companies with minimal manual intervention

### Success Metrics
- **Reliability:** >95% successful runs per company per week
- **Data Quality:** <2% silent data corruption incidents
- **Scalability:** Support 10x company growth without architectural changes
- **Developer Velocity:** New scraper deployment <2 hours
- **Operational Load:** <5 hours/week maintenance time

---

## Business Context

### Strategic Goals
1. **Scale to 500-1,000 Companies:** Infrastructure must handle 10x current volume
2. **Data Product Foundation:** Enable hiring indices, trend analysis, and market intelligence
3. **Lifestyle Business Model:** Maximum automation, minimal manual intervention
4. **Multi-Market Expansion:** Support Germany, UK, Spain, Italy, France, USA
5. **Programmatic SEO:** Generate 1,500-2,000 word company analysis pages automatically

### Revenue Streams Enabled
- B2C career guidance services
- Premium subscriptions
- Display advertising
- Affiliate marketing
- B2B data licensing (future)

### Key Constraints
- Solo founder operation (no team scaling)
- €200/hour minimum rate requirement (time = money)
- Budget consciousness: pragmatic over perfect
- Must maintain current scraping while migrating

---

## Problem Statement

### Critical Issues

#### 1. Data Integrity Risks
**Problem:** Silent data corruption from failed scrapes marking all jobs as inactive
- No validation of response quality before updating master lists
- Race conditions when multiple runs access same company
- No confidence scoring for run results

**Impact:** Corrupted hiring indices, incorrect trend analysis, user trust loss

#### 2. Security & Operational Risks
**Problem:** Hardcoded credentials in source code
- DB credentials in `db_runs.py`
- Proxy credentials in `util_v5.py`
- Local file paths in production code
- No secret rotation capability

**Impact:** Security vulnerability, cannot share code, difficult cloud deployment

#### 3. Scalability Bottlenecks
**Problem:** GCS JSON master lists with O(N²) lookups
- Linear search for each job ID
- Full file download/upload for each update
- No transactional guarantees
- Becomes prohibitively slow at scale

**Impact:** Cannot scale beyond 200-300 companies efficiently

#### 4. Poor Observability
**Problem:** Cannot diagnose failures or understand system health
- Binary success/fail status insufficient
- No distinction between rate limits, blocks, parsing errors
- No stage-level performance tracking
- Cannot identify which companies are problematic

**Impact:** Blind debugging, wasted time, missed revenue opportunities

#### 5. Fragmented Architecture
**Problem:** Each scraper is a unique snowflake
- JSON scrapers vs HTML scrapers have no shared patterns
- No standardized error handling
- Duplicate code across scrapers
- Difficult to apply fixes/improvements systematically

**Impact:** High maintenance burden, slow feature rollout, technical debt accumulation

---

## Solution Overview

### Architecture Principles

1. **Postgres-First for Structured Data:** Master job listings, metadata, and metrics in relational database
2. **GCS for BLOBs Only:** Job detail texts, snapshots, and audit trails
3. **Unified Scraper Templates:** Standardized patterns for JSON, HTML, and hybrid approaches
4. **Fail-Safe by Default:** Data quality checks before destructive operations
5. **Observable at Every Layer:** Structured logging, metrics, and confidence scoring
6. **Incremental Migration:** Parallel operation during transition, graceful fallbacks

### Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     Cloud Scheduler + Pub/Sub                    │
│                    (Orchestration & Triggers)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Cloud Run Jobs                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ JSON Scraper │  │ HTML Scraper │  │ Hybrid       │         │
│  │ Template     │  │ Template     │  │ Scraper      │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                  │                  │                  │
│         └──────────────────┴──────────────────┘                 │
│                            │                                     │
│                            ▼                                     │
│              ┌──────────────────────────┐                       │
│              │ Unified Scraper Core     │                       │
│              │ - Error Classification   │                       │
│              │ - Confidence Scoring     │                       │
│              │ - HTTP Stats Collection  │                       │
│              │ - Retry Logic            │                       │
│              └──────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                 ┌────────────┴────────────┐
                 ▼                          ▼
┌─────────────────────────────┐  ┌─────────────────────────┐
│   Cloud SQL (Postgres)      │  │   Cloud Storage (GCS)   │
│   - jobs                    │  │   - Detail texts        │
│   - scrape_runs             │  │   - Daily snapshots     │
│   - company_configs         │  │   - Audit trail         │
│   - scrape_locks            │  │                         │
└─────────────────────────────┘  └─────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              Cloud Logging + Looker Studio                       │
│              (Monitoring & Analytics)                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Functional Requirements

### FR-1: Data Storage Migration

#### FR-1.1: Postgres Schema Design
**Priority:** P0  
**Effort:** 2-3 days

**Requirements:**
- Design normalized schema for job listings with proper indexing
- Support for job metadata, status tracking, and history
- Efficient querying for dashboards and analytics
- Partitioning strategy for long-term data growth

**Acceptance Criteria:**
- Schema supports 10M+ rows without performance degradation
- Query response times <500ms for dashboard queries
- Migration path from existing GCS data defined
- Rollback plan documented

**Tables Required:**
```sql
-- Core job listings
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    company_key TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    department TEXT,
    posted_date DATE,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    status TEXT CHECK (status IN ('active', 'inactive')),
    detail_gcs_path TEXT,
    detail_fetched_at TIMESTAMPTZ,
    meta JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Company configuration and feature flags
CREATE TABLE company_configs (
    company_key TEXT PRIMARY KEY,
    enabled BOOLEAN DEFAULT true,
    safe_mode BOOLEAN DEFAULT false,
    scraper_version TEXT DEFAULT 'v1',
    parser_version TEXT DEFAULT 'legacy',
    auto_disabled_at TIMESTAMPTZ,
    auto_disabled_reason TEXT,
    retry_after TIMESTAMPTZ,
    meta JSONB
);

-- Concurrency control
CREATE TABLE scrape_locks (
    company_key TEXT PRIMARY KEY,
    locked_at TIMESTAMPTZ NOT NULL,
    locked_by TEXT,
    expires_at TIMESTAMPTZ NOT NULL
);

-- Enhanced scrape_runs (existing table extended)
ALTER TABLE scrape_runs ADD COLUMN IF NOT EXISTS confidence_score FLOAT;
ALTER TABLE scrape_runs ADD COLUMN IF NOT EXISTS stage TEXT;
ALTER TABLE scrape_runs ADD COLUMN IF NOT EXISTS http_stats JSONB;
```

#### FR-1.2: GCS Data Migration
**Priority:** P0  
**Effort:** 1-2 days

**Requirements:**
- One-time migration script to load existing master lists into Postgres
- Data validation during migration (check for duplicates, missing fields)
- Preserve historical timestamps (first_seen, last_updated)
- Generate migration report (success/failure counts per company)

**Acceptance Criteria:**
- 100% of existing job data migrated successfully
- No data loss (verified via checksum/count comparison)
- Migration can be rolled back if issues found
- Historical timestamps preserved accurately

#### FR-1.3: Dual-Write Period
**Priority:** P0  
**Effort:** 1 day

**Requirements:**
- Scrapers write to both Postgres and GCS during transition
- Automated comparison to detect discrepancies
- Fallback to GCS if Postgres unavailable
- Configurable cutover date per company

**Acceptance Criteria:**
- Both storage systems contain identical data (verified daily)
- <1% discrepancy rate during dual-write period
- Smooth cutover without downtime
- Rollback capability if needed

---

### FR-2: Security & Configuration Management

#### FR-2.1: Secrets Externalization
**Priority:** P0  
**Effort:** 1 day

**Requirements:**
- Remove all hardcoded credentials from source code
- Use environment variables for all secrets
- Integrate with Google Secret Manager for production
- Fail-fast validation on startup (clear error messages if secrets missing)

**Secrets to Externalize:**
- Database connection strings (host, user, password, database)
- Proxy credentials (username, password)
- GCS service account keys (use workload identity where possible)
- API keys for external services

**Acceptance Criteria:**
- Zero credentials in source code (verified via regex scan)
- All scrapers load secrets from environment/Secret Manager
- Startup validation fails with clear message if secrets missing
- Documentation for local development secret setup

#### FR-2.2: Configuration System
**Priority:** P1  
**Effort:** 2-3 days

**Requirements:**
- Centralized configuration management (YAML/JSON files or DB)
- Per-company scraper configuration (URLs, pagination, timeouts)
- Environment-specific configs (dev, staging, prod)
- Hot-reload capability for non-destructive config changes

**Configuration Hierarchy:**
```
configs/
├── default.yaml           # Global defaults
├── companies/
│   ├── audi.yaml         # Company-specific overrides
│   ├── bmw.yaml
│   └── ...
└── environments/
    ├── dev.yaml
    ├── staging.yaml
    └── prod.yaml
```

**Acceptance Criteria:**
- Config changes don't require code deployment
- Config validation on load (schema validation)
- Per-company overrides work correctly
- Rollback to previous config version possible

---

### FR-3: Unified Scraper Architecture

#### FR-3.1: Scraper Template System
**Priority:** P0  
**Effort:** 3-5 days

**Requirements:**
- Abstract base scraper class with common functionality
- Specialized templates for JSON, HTML, and hybrid approaches
- Plugin architecture for custom parsing logic
- Shared error handling and retry mechanisms

**Template Types:**

1. **JSON API Template**
   - Hidden API discovery pattern
   - JSON parsing with nested value extraction
   - Pagination handling (offset, page, cursor)
   - Response validation

2. **HTML Static Template**
   - BeautifulSoup/lxml-based parsing
   - CSS selector configuration
   - Structured data extraction (JSON-LD, microdata)
   - Rate limiting and politeness delays

3. **Hybrid Template**
   - Initial HTML page load for session/cookies
   - Subsequent API calls for data
   - Anti-bot circumvention patterns
   - Session management

**Common Features Across Templates:**
- HTTP stats collection
- Confidence scoring
- Error classification
- Stage tracking
- Checkpoint/resume capability

**Acceptance Criteria:**
- Existing JSON scrapers migrated to new template (5 scrapers as POC)
- Existing HTML scrapers migrated to new template (3 scrapers as POC)
- Code reuse >70% across similar scrapers
- Performance parity or better vs current implementation

#### FR-3.2: Error Classification System
**Priority:** P0  
**Effort:** 2 days

**Requirements:**
- Structured exception hierarchy for different failure modes
- Automatic classification based on symptoms
- Appropriate retry strategies per error type
- Error context captured for debugging

**Error Classes:**
```python
# Base
class ScraperError(Exception): pass

# Network/HTTP
class RateLimitError(ScraperError): pass       # 429, Retry-After
class BlockedError(ScraperError): pass         # 403, WAF detected
class ProxyError(ScraperError): pass           # Proxy timeout/failure
class TimeoutError(ScraperError): pass         # Request timeout

# Data/Parsing
class ParseError(ScraperError): pass           # Cannot extract data
class ValidationError(ScraperError): pass      # Data fails quality checks
class EmptyResponseError(ScraperError): pass   # Zero jobs returned

# Infrastructure
class DatabaseError(ScraperError): pass        # DB connection issues
class StorageError(ScraperError): pass         # GCS upload failures

# Configuration
class ConfigError(ScraperError): pass          # Missing/invalid config
```

**Retry Logic:**
- RateLimitError: Exponential backoff respecting Retry-After header
- BlockedError: Switch proxy/route, circuit breaker after 3 consecutive
- ProxyError: Rotate to different proxy immediately
- TimeoutError: Retry with increased timeout (up to 3x)
- ParseError: No retry, mark as failed
- DatabaseError: Retry 3x with linear backoff
- ConfigError: Fail fast, no retry

**Acceptance Criteria:**
- All error types properly classified in production
- Retry strategies reduce transient failure rate by >50%
- Circuit breaker prevents wasteful retry loops
- Error context sufficient for debugging (logged with run_id, company_key, stage)

#### FR-3.3: Run Confidence Scoring
**Priority:** P0  
**Effort:** 2-3 days

**Requirements:**
- Calculate confidence score (0.0-1.0) for each scrape run
- Based on multiple signals: job count, parse rate, HTTP errors, content validation
- Configurable thresholds for different actions
- Prevent data corruption from low-confidence runs

**Scoring Algorithm:**
```python
def calculate_confidence(run_stats):
    score = 1.0
    
    # Job count plausibility (vs historical average)
    if jobs_fetched == 0: score = 0.0
    elif jobs_fetched < expected_min * 0.5: score *= 0.6
    
    # Parse success rate
    parse_rate = jobs_processed / max(jobs_fetched, 1)
    score *= parse_rate
    
    # HTTP error rate
    error_rate = requests_failed / requests_total
    score *= (1 - error_rate)
    
    # Block/rate limit signals
    block_rate = (status_403 + status_429) / requests_total
    score *= (1 - block_rate * 2)
    
    # Content validation
    if unexpected_content_type: score *= 0.5
    
    return max(0.0, min(1.0, score))
```

**Action Thresholds:**
- **Confidence ≥ 0.8:** High quality - mark inactive jobs, update indices
- **Confidence 0.5-0.79:** Partial - save new jobs, DO NOT mark inactive
- **Confidence < 0.5:** Failed - discard data, alert

**Acceptance Criteria:**
- Confidence score calculated for 100% of runs
- Zero false-positive inactive markings in 2-week testing period
- Low-confidence runs properly identified (manual review of 20 samples)
- Score logged and available in dashboard

---

### FR-4: Monitoring & Observability

#### FR-4.1: Structured Logging
**Priority:** P1  
**Effort:** 1-2 days

**Requirements:**
- JSON-structured logs with consistent schema
- Correlation IDs (run_id) across all log entries
- Log levels used appropriately (DEBUG/INFO/WARNING/ERROR)
- Integration with Cloud Logging

**Standard Log Fields:**
```json
{
  "timestamp": "2026-01-26T10:30:00Z",
  "level": "INFO",
  "run_id": "uuid-here",
  "company_key": "audi",
  "stage": "fetch_list",
  "message": "Fetched 150 jobs successfully",
  "metrics": {
    "jobs_fetched": 150,
    "http_requests": 5,
    "duration_ms": 2340
  }
}
```

**Acceptance Criteria:**
- 100% of scraper logs use structured format
- Cloud Logging queries work for common debugging scenarios
- Log volume <10MB per company per day
- Sensitive data (credentials, PII) never logged

#### FR-4.2: Stage Duration Tracking
**Priority:** P1  
**Effort:** 1 day

**Requirements:**
- Track time spent in each scraping stage
- Identify performance bottlenecks
- Alert on abnormally slow stages
- Store in scrape_runs table for historical analysis

**Stages to Track:**
- `init`: Configuration loading and validation
- `fetch_list`: Fetching job listings
- `parse_list`: Parsing and extracting job data
- `fetch_details`: Fetching individual job details (if applicable)
- `save_db`: Writing to Postgres
- `save_gcs`: Uploading to GCS
- `finalize`: Marking inactive, cleanup

**Acceptance Criteria:**
- Stage durations captured for all runs
- Dashboard shows p50/p95/p99 by stage and company
- Alerts triggered for >3x normal duration
- Historical data available for trend analysis

#### FR-4.3: HTTP Request Metrics
**Priority:** P1  
**Effort:** 2 days

**Requirements:**
- Aggregate HTTP stats per run (already partially implemented)
- Track status code distribution
- Monitor proxy performance
- Detect block/rate limit patterns

**Metrics to Collect:**
```python
{
  "requests_total": 45,
  "requests_ok": 42,        # 2xx/3xx
  "requests_failed": 3,     # Exceptions/timeouts
  "status_counts": {
    "200": 40,
    "403": 2,
    "429": 1,
    "500": 2
  },
  "exception_counts": {
    "ReadTimeout": 2,
    "ProxyError": 1
  },
  "timeouts": 2,
  "latency_ms_total": 45000,
  "latency_ms_avg": 1000,
  "last_error": "ReadTimeout: proxy.example.com"
}
```

**Acceptance Criteria:**
- HTTP stats stored in scrape_runs.http_stats (JSONB)
- Dashboard shows success rates and latency trends
- Alerts for >10% 403/429 rate
- Proxy performance comparable across runs

#### FR-4.4: Dashboard & Alerting
**Priority:** P1  
**Effort:** 2-3 days

**Requirements:**
- Looker Studio dashboard for real-time monitoring
- Automated alerts for critical conditions
- Historical trends for capacity planning
- Per-company health scores

**Dashboard Views:**

1. **Overview**
   - Success rate last 24h/7d/30d
   - Total active jobs
   - Companies in safe mode/disabled
   - Alert summary

2. **Run Details**
   - Recent runs by company
   - Confidence scores
   - Stage durations
   - Error distribution

3. **HTTP Performance**
   - Status code trends
   - Proxy health
   - Latency percentiles
   - Block/rate limit incidents

4. **Data Quality**
   - Jobs added/removed trends
   - Parse success rates
   - Missing field analysis
   - Suspicious runs flagged

**Alert Conditions:**
- 3+ consecutive failures for any company
- Confidence score <0.5 for 3+ runs
- >20% of runs blocked (403) in 24h
- Database connection failures
- Budget exceeded (requests, runtime, bandwidth)

**Acceptance Criteria:**
- Dashboard accessible to authorized users
- Auto-refresh every 5 minutes
- Alerts delivered via email/Slack within 5 minutes
- False positive rate <5%

---

### FR-5: Operational Resilience

#### FR-5.1: Concurrency Control & Locking
**Priority:** P0  
**Effort:** 1-2 days

**Requirements:**
- Prevent multiple concurrent runs for same company
- DB-based locking mechanism with TTL
- Automatic lock expiration for crashed runs
- Graceful handling of lock conflicts

**Implementation:**
```sql
CREATE TABLE scrape_locks (
    company_key TEXT PRIMARY KEY,
    locked_at TIMESTAMPTZ NOT NULL,
    locked_by TEXT,  -- run_id
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > locked_at)
);

-- Auto-cleanup expired locks
CREATE INDEX idx_lock_expires ON scrape_locks(expires_at);
```

**Lock Acquisition Logic:**
```python
# Acquire lock (30-minute TTL)
INSERT INTO scrape_locks (company_key, locked_at, locked_by, expires_at)
VALUES (%s, NOW(), %s, NOW() + INTERVAL '30 minutes')
ON CONFLICT (company_key) DO UPDATE
SET locked_at = EXCLUDED.locked_at,
    locked_by = EXCLUDED.locked_by,
    expires_at = EXCLUDED.expires_at
WHERE scrape_locks.expires_at < NOW()
RETURNING company_key;

# If no rows returned → already locked
```

**Acceptance Criteria:**
- Zero race conditions in 2-week testing period
- Locks automatically released on run completion
- Expired locks cleaned up without manual intervention
- Lock conflicts logged and handled gracefully

#### FR-5.2: Checkpoint & Resume
**Priority:** P1  
**Effort:** 2-3 days

**Requirements:**
- Save progress at regular intervals during run
- Resume from last checkpoint on restart/failure
- Idempotent operations (safe to re-process)
- Configurable checkpoint granularity

**Checkpoint Strategy:**
- Checkpoint after fetching job list
- Checkpoint every 50 jobs processed
- Checkpoint before marking inactive jobs

**Implementation:**
```python
# Save checkpoint
UPDATE scrape_runs 
SET stage = %s, 
    meta = meta || %s::jsonb
WHERE run_id = %s;

# Resume from checkpoint
checkpoint = get_checkpoint(run_id)
if checkpoint['stage'] == 'fetch_list' and checkpoint.get('job_list'):
    job_list = checkpoint['job_list']
    # Skip fetch, go to parse
else:
    # Start from beginning
```

**Acceptance Criteria:**
- Runs successfully resume after simulated crash (10 test cases)
- No duplicate data from resumed runs
- Resume overhead <5% of total runtime
- Checkpoint data size <100KB per run

#### FR-5.3: Kill Switch & Safe Mode
**Priority:** P1  
**Effort:** 1-2 days

**Requirements:**
- Automatic disabling of problematic companies
- Safe mode (list-only, no details) for degraded operation
- Manual enable/disable via admin interface
- Auto-retry after cooldown period

**Trigger Conditions:**
- 3+ consecutive failures → 24h cooldown
- Confidence <0.5 for 5+ runs → manual review required
- Budget exceeded → disable until admin review
- Manual disable for maintenance

**Safe Mode Behavior:**
- Fetch job listings only (no detail pages)
- Reduced request rate
- No inactive marking (preserve existing data)
- Flag for admin review

**Acceptance Criteria:**
- Auto-disable prevents runaway failures
- Safe mode successfully degrades service without total failure
- Cooldown periods configurable per company
- Admin interface for manual control (even if just SQL)

#### FR-5.4: Budget Guards
**Priority:** P2  
**Effort:** 1 day

**Requirements:**
- Hard limits on resource consumption per run
- Graceful shutdown when budget exceeded
- Alerts for approaching limits
- Configurable budgets per company

**Budget Types:**
- Max requests per run (default: 500)
- Max runtime (default: 10 minutes)
- Max bytes downloaded (default: 50MB)
- Max proxy cost per run (calculated estimate)

**Enforcement:**
```python
if run_stats['requests_total'] > MAX_REQUESTS:
    raise BudgetExceeded("Max requests exceeded")

if time.time() - start_time > MAX_RUNTIME:
    raise BudgetExceeded("Max runtime exceeded")
```

**Acceptance Criteria:**
- Budget violations properly detected and logged
- Runs terminate gracefully (no data corruption)
- Alerts sent for budget violations
- Budget limits adjustable per company

---

### FR-6: Testing & Quality Assurance

#### FR-6.1: Golden Fixtures / Contract Tests
**Priority:** P1  
**Effort:** 2-3 days

**Requirements:**
- Capture real API responses as test fixtures (sanitized)
- Contract tests validate parser against fixtures
- Detect breaking API changes before production
- Support offline development/testing

**Fixture Structure:**
```
tests/fixtures/
├── companies/
│   ├── audi/
│   │   ├── list_response.json
│   │   ├── detail_response.json
│   │   └── empty_response.json
│   ├── bmw/
│   │   └── ...
```

**Test Coverage:**
- Happy path: Extract jobs from typical response
- Empty response: Handle zero results gracefully
- Malformed response: Proper error handling
- Edge cases: Missing fields, unusual data types

**Acceptance Criteria:**
- Contract tests for top 20 companies (by priority)
- Tests pass consistently in CI
- API changes detected within 24 hours
- Test execution time <30 seconds total

#### FR-6.2: Integration Testing
**Priority:** P2  
**Effort:** 2-3 days

**Requirements:**
- End-to-end tests against staging environment
- Smoke tests for critical companies daily
- Load testing for database at scale
- Rollback testing for migration scenarios

**Test Scenarios:**
- Full scrape run for 5 companies
- Database migration and rollback
- Lock acquisition under concurrency
- Checkpoint and resume
- Error recovery (simulated failures)

**Acceptance Criteria:**
- Integration tests run in CI on every PR
- Smoke tests run daily against production (non-destructive)
- Load tests validate 1,000 company capacity
- Test environment mirrors production architecture

---

## Non-Functional Requirements

### NFR-1: Performance

#### NFR-1.1: Scraping Speed
- Single company scrape: <5 minutes (p95)
- 1,000 companies: <6 hours total (with parallelism)
- Database queries: <500ms (p95)
- Dashboard load time: <2 seconds

#### NFR-1.2: Scalability
- Support 10M+ job records without schema changes
- Handle 1,000 concurrent scrape jobs
- Database connection pool: 20-50 connections
- Horizontal scaling via Cloud Run parallelism

### NFR-2: Reliability

#### NFR-2.1: Uptime & Availability
- Scraping infrastructure: 99% uptime
- Database: 99.9% availability (managed service SLA)
- Data freshness: <24 hours for any company

#### NFR-2.2: Data Durability
- Zero data loss from infrastructure failures
- Postgres: ACID compliance, point-in-time recovery
- GCS: 99.999999999% durability (11 9s)
- Daily automated backups with 30-day retention

### NFR-3: Security

#### NFR-3.1: Credential Management
- Zero hardcoded secrets in source code
- Secrets stored in Google Secret Manager
- Service account with least-privilege permissions
- Automatic credential rotation (90 days)

#### NFR-3.2: Data Privacy
- No PII scraped or stored
- Logs sanitized (no credentials, no email addresses)
- GCS buckets private (no public access)
- Database access restricted to authorized IPs

### NFR-4: Maintainability

#### NFR-4.1: Code Quality
- Code coverage >70% for core modules
- Type hints for all public functions
- Docstrings for all modules/classes
- Linting (flake8, black) passes in CI

#### NFR-4.2: Documentation
- Architecture diagram up-to-date
- Runbook for common operations
- Scraper configuration guide
- Deployment procedures documented

### NFR-5: Cost Efficiency

#### NFR-5.1: Infrastructure Costs
- Target: <€100/month for 500 companies
- Supabase/Cloud SQL: ~€25-50/month
- GCS storage: <€5/month
- Cloud Run: <€30/month (with efficient scheduling)
- Proxy services: <€20/month

#### NFR-5.2: Operational Costs
- Maintenance time: <5 hours/week
- On-call incidents: <2 per month
- Deployment frequency: 1-2x per week
- Zero downtime deployments

---

## Technical Specifications

### Tech Stack

#### Infrastructure
- **Compute:** Google Cloud Run Jobs (serverless, auto-scaling)
- **Orchestration:** Cloud Scheduler + Pub/Sub
- **Database:** Supabase (PostgreSQL) or Cloud SQL PostgreSQL
- **Object Storage:** Google Cloud Storage
- **Monitoring:** Cloud Logging, Looker Studio
- **Secrets:** Google Secret Manager

#### Languages & Frameworks
- **Primary Language:** Python 3.11+
- **HTTP Client:** requests (current), consider httpx (future)
- **Database Driver:** psycopg 3 (with connection pooling)
- **Parsing:** BeautifulSoup4, lxml, json
- **Testing:** pytest, pytest-mock

#### Development Tools
- **Version Control:** Git (current repo)
- **CI/CD:** GitHub Actions or Cloud Build
- **Code Quality:** black, flake8, mypy
- **Package Management:** pip with requirements.txt (consider poetry)

### Database Schema (Complete)

```sql
-- Jobs table (primary data)
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    company_key TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    department TEXT,
    posted_date DATE,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    detail_gcs_path TEXT,
    detail_fetched_at TIMESTAMPTZ,
    meta JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_company_status ON jobs(company_key, status);
CREATE INDEX idx_jobs_last_seen ON jobs(last_seen);
CREATE INDEX idx_jobs_posted_date ON jobs(posted_date);
CREATE INDEX idx_jobs_company_posted ON jobs(company_key, posted_date DESC);
CREATE INDEX idx_jobs_meta_gin ON jobs USING gin(meta);

-- Scrape runs (enhanced existing table)
CREATE TABLE scrape_runs (
    run_id TEXT PRIMARY KEY,
    company_key TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN (
        'running', 'success', 'partial_success', 'failed', 
        'blocked', 'rate_limited', 'empty_suspect', 'parse_error',
        'dependency_error', 'config_error', 'budget_exceeded',
        'failed_low_confidence'
    )),
    stage TEXT,
    confidence_score FLOAT CHECK (confidence_score BETWEEN 0 AND 1),
    execution_time_sec FLOAT,
    cpu_usage_pct FLOAT,
    jobs_fetched INTEGER,
    jobs_processed INTEGER,
    new_jobs INTEGER,
    inactive_jobs INTEGER,
    skipped_jobs INTEGER,
    error_message TEXT,
    http_stats JSONB,
    stage_durations JSONB,  -- {"fetch_list": 2.3, "parse": 1.1, ...}
    meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_runs_company_started ON scrape_runs(company_key, started_at DESC);
CREATE INDEX idx_runs_status ON scrape_runs(status);
CREATE INDEX idx_runs_started ON scrape_runs(started_at DESC);

-- Company configuration
CREATE TABLE company_configs (
    company_key TEXT PRIMARY KEY,
    enabled BOOLEAN DEFAULT true,
    safe_mode BOOLEAN DEFAULT false,
    scraper_version TEXT DEFAULT 'v1',
    parser_version TEXT DEFAULT 'legacy',
    use_new_proxy_strategy BOOLEAN DEFAULT false,
    use_confidence_scoring BOOLEAN DEFAULT true,
    auto_disabled_at TIMESTAMPTZ,
    auto_disabled_reason TEXT,
    retry_after TIMESTAMPTZ,
    expected_job_count_min INTEGER,
    expected_job_count_max INTEGER,
    max_requests_per_run INTEGER DEFAULT 500,
    max_runtime_sec INTEGER DEFAULT 600,
    meta JSONB DEFAULT '{}'::jsonb
);

-- Scrape locks
CREATE TABLE scrape_locks (
    company_key TEXT PRIMARY KEY,
    locked_at TIMESTAMPTZ NOT NULL,
    locked_by TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > locked_at)
);

CREATE INDEX idx_lock_expires ON scrape_locks(expires_at);

-- Cleanup function for expired locks (run via cron)
CREATE OR REPLACE FUNCTION cleanup_expired_locks()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM scrape_locks WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
```

### GCS Bucket Structure

```
{BUCKET_NAME}/
├── detail_texts/
│   ├── {company_key}/
│   │   ├── {job_id}.txt
│   │   └── ...
├── snapshots/
│   ├── daily/
│   │   ├── {YYYY-MM-DD}/
│   │   │   ├── {company_key}.json.gz
│   │   │   └── ...
│   └── monthly/
│       └── {YYYY-MM}/
│           └── full_snapshot.parquet
└── archives/
    └── master_lists_legacy/  # Old GCS master lists (pre-migration)
        └── {company_key}_master.json
```

### Configuration File Format

```yaml
# configs/companies/audi.yaml
company_key: audi
display_name: "Audi AG"
enabled: true
scraper_version: v2

# Scraping configuration
scraping:
  template: json_api
  base_url: "https://audi.career.softgarden.de/api/vacancies"
  
  # Pagination
  pagination:
    enabled: true
    mode: offset  # offset | page | cursor
    page_size: 50
    max_pages: 10
  
  # Headers
  headers:
    User-Agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    Accept: "application/json"
  
  # Field mapping
  fields:
    job_id: ["data", "id"]
    title: ["data", "attributes", "title"]
    location: ["data", "attributes", "location"]
    posted_date: ["data", "attributes", "publishedAt"]
  
  # Proxy configuration
  proxy:
    enabled: true
    strategy: adaptive  # always | adaptive | fallback
    country: DE

# Quality thresholds
quality:
  expected_job_count_min: 50
  expected_job_count_max: 500
  confidence_threshold: 0.7

# Budget limits
budget:
  max_requests: 200
  max_runtime_sec: 300
  max_bytes_downloaded: 10485760  # 10MB
```

---

## Implementation Roadmap

### Phase 0: Foundation (Week 1-2)

**Goals:** Security, database setup, eliminate critical risks

**Tasks:**
1. ✅ Externalize all secrets to environment variables
2. ✅ Set up Supabase/Cloud SQL Postgres instance
3. ✅ Design and create database schema
4. ✅ Implement connection pooling in `db_runs.py`
5. ✅ Create migration script (GCS → Postgres)
6. ✅ Run migration for 5 test companies
7. ✅ Validate migrated data

**Deliverables:**
- Zero hardcoded credentials in codebase
- Postgres database operational with schema
- 5 companies migrated successfully
- Migration runbook documented

**Success Criteria:**
- Security scan passes (no credentials found)
- Database queries functional
- Migrated data matches GCS data 100%

---

### Phase 1: Core Robustness (Week 3-4)

**Goals:** Prevent data corruption, improve error handling

**Tasks:**
1. ✅ Implement granular exception classes
2. ✅ Build run confidence scoring system
3. ✅ Add empty/suspicious response checks
4. ✅ Implement DB-based locking (prevent race conditions)
5. ✅ Add stage duration tracking
6. ✅ Implement structured logging
7. ✅ Migrate 20 companies to Postgres
8. ✅ Enable dual-write mode (Postgres + GCS)

**Deliverables:**
- Error classification system operational
- Confidence scoring prevents bad data writes
- Zero race conditions in 1-week test
- Structured logs in Cloud Logging

**Success Criteria:**
- 20 companies running on new system without issues
- No false-positive inactive markings
- All errors properly classified
- Logs queryable for debugging

---

### Phase 2: Unified Architecture (Week 5-7)

**Goals:** Consolidate scraper templates, enable scalability

**Tasks:**
1. ✅ Design base scraper class + template system
2. ✅ Implement JSON API template
3. ✅ Implement HTML static template
4. ✅ Migrate 10 JSON scrapers to new template
5. ✅ Migrate 5 HTML scrapers to new template
6. ✅ Create configuration system (YAML files)
7. ✅ Implement checkpoint/resume mechanism
8. ✅ Build kill switch + safe mode

**Deliverables:**
- Unified scraper architecture with templates
- 15 scrapers refactored and operational
- Config-driven scraper behavior
- Resume-on-failure capability

**Success Criteria:**
- Code duplication reduced by >60%
- New scraper deployment time <2 hours
- Scrapers resume successfully after simulated crash
- Safe mode prevents runaway failures

---

### Phase 3: Observability & Quality (Week 8-9)

**Goals:** Full visibility, automated quality assurance

**Tasks:**
1. ✅ Build Looker Studio dashboard
2. ✅ Implement alerting rules
3. ✅ Create golden fixtures for top 20 companies
4. ✅ Set up CI with contract tests
5. ✅ Implement budget guards
6. ✅ Add HTTP metrics visualization
7. ✅ Complete dual-write validation

**Deliverables:**
- Operational dashboard with real-time metrics
- Automated alerts for failures
- Contract tests in CI
- Budget protection active

**Success Criteria:**
- Dashboard accessible and auto-refreshing
- Alerts trigger within 5 minutes of incident
- Contract tests detect API changes
- Budget violations prevented

---

### Phase 4: Cloud Migration (Week 10-12)

**Goals:** Move from GCE to Cloud Run, full automation

**Tasks:**
1. ✅ Containerize scrapers (Docker)
2. ✅ Set up Cloud Run Jobs
3. ✅ Configure Cloud Scheduler + Pub/Sub
4. ✅ Migrate 50 companies to Cloud Run
5. ✅ Implement graceful scaling
6. ✅ Cut over from GCS master lists to Postgres
7. ✅ Decommission old shell scripts

**Deliverables:**
- All scrapers running on Cloud Run Jobs
- Automated scheduling via Cloud Scheduler
- GCS master lists deprecated
- Old infrastructure decommissioned

**Success Criteria:**
- 100% of companies on new infrastructure
- Cost within budget (€100/month)
- No manual intervention required for 1 week
- Rollback plan validated

---

### Phase 5: Scale & Optimize (Week 13+)

**Goals:** Scale to 500+ companies, optimize costs

**Tasks:**
1. ✅ Implement feature flags for gradual rollout
2. ✅ Add remaining 380+ companies (125 → 500)
3. ✅ Optimize database queries (indexes, caching)
4. ✅ Implement adaptive proxy strategies
5. ✅ Build admin interface for company management
6. ✅ Performance tuning (reduce runtime by 30%)
7. ✅ Cost optimization (reduce per-company cost)

**Deliverables:**
- 500+ companies scraped daily
- Optimized database performance
- Admin tools for operations
- Comprehensive documentation

**Success Criteria:**
- 500 companies complete in <6 hours
- Database queries remain <500ms
- Cost per company <€0.20/month
- Maintenance time <5 hours/week

---

## Risk Assessment

### High-Priority Risks

#### Risk 1: Data Corruption During Migration
**Probability:** Medium  
**Impact:** High  
**Mitigation:**
- Dual-write period with daily validation
- Automated comparison between GCS and Postgres
- Rollback plan with GCS snapshots
- Migration for 5 companies before scaling

#### Risk 2: Database Performance at Scale
**Probability:** Low  
**Impact:** High  
**Mitigation:**
- Load testing before full rollout
- Database indexing strategy reviewed
- Partitioning plan for >10M rows
- Query optimization and caching

#### Risk 3: API/Scraper Breaking Changes
**Probability:** Medium  
**Impact:** Medium  
**Mitigation:**
- Golden fixtures detect changes immediately
- Contract tests in CI
- Alerts for parser failure rate >10%
- Safe mode prevents runaway failures

#### Risk 4: Cost Overruns
**Probability:** Low  
**Impact:** Medium  
**Mitigation:**
- Budget guards per run
- Cost monitoring dashboard
- Alert for >€150/month spend
- Optimistic scaling (start conservative)

### Medium-Priority Risks

#### Risk 5: Proxy Service Reliability
**Probability:** Medium  
**Impact:** Medium  
**Mitigation:**
- Health tracking per proxy route
- Multiple proxy providers (backup)
- Fallback to direct connection
- Circuit breaker for blocked proxies

#### Risk 6: Cloud Run Cold Starts
**Probability:** Low  
**Impact:** Low  
**Mitigation:**
- Minimum instances = 0 (cost) vs 1 (performance)
- Warm-up requests if needed
- Optimize container size (<500MB)
- Benchmark cold start impact

---

## Success Metrics & KPIs

### Data Quality Metrics
- **Silent Data Corruption Rate:** <2% (target: 0%)
- **Confidence Score Average:** >0.85
- **Parse Success Rate:** >95%
- **Inactive Jobs False Positive Rate:** <1%

### Reliability Metrics
- **Scraper Success Rate:** >95% per company per week
- **Infrastructure Uptime:** >99%
- **Database Availability:** >99.9%
- **Mean Time to Recovery (MTTR):** <30 minutes

### Performance Metrics
- **Scrape Duration (p95):** <5 minutes per company
- **Database Query Time (p95):** <500ms
- **Dashboard Load Time:** <2 seconds
- **Jobs Processed Per Hour:** >10,000

### Operational Metrics
- **Maintenance Time:** <5 hours/week
- **Deployment Frequency:** 1-2x per week
- **On-Call Incidents:** <2 per month
- **New Scraper Deployment Time:** <2 hours

### Cost Metrics
- **Infrastructure Cost:** <€100/month (500 companies)
- **Cost Per Company:** <€0.20/month
- **Proxy Cost Per Run:** <€0.05
- **Total Operating Cost:** <€120/month

---

## Appendices

### Appendix A: Glossary

- **Confidence Score:** Numerical score (0.0-1.0) indicating data quality of a scrape run
- **Dual-Write:** Temporary period where data is written to both old (GCS) and new (Postgres) storage
- **Golden Fixture:** Saved API response used for regression testing
- **Grace Period:** Time window before marking unseen jobs as inactive (prevents false positives)
- **Kill Switch:** Mechanism to automatically disable problematic scrapers
- **Master List:** Historical term for GCS-based job inventory (deprecated in favor of Postgres)
- **Safe Mode:** Degraded operation mode (list-only, no details, no inactive marking)
- **Scraper Template:** Reusable code pattern for specific scraping approach (JSON/HTML/hybrid)
- **Stage:** Distinct phase of scraping process (fetch, parse, save, etc.)

### Appendix B: Related Documents

- Architecture Diagram (TBD)
- API Documentation (TBD)
- Deployment Runbook (TBD)
- Monitoring Dashboard Guide (TBD)
- Incident Response Playbook (TBD)

### Appendix C: Decision Log

| Date | Decision | Rationale | Owner |
|------|----------|-----------|-------|
| 2026-01-26 | Postgres over GCS for master lists | Better queries, ACID, no race conditions | Sebastian |
| 2026-01-26 | Keep detail texts in GCS | BLOBs don't belong in relational DB | Sebastian |
| 2026-01-26 | Confidence scoring mandatory | Prevents data corruption from bad runs | Sebastian |
| 2026-01-26 | Defer full async/parallel | Complexity > benefit at current scale | Sebastian |

---

## Approval & Sign-off

**Document Owner:** Sebastian Winkler  
**Date Created:** January 26, 2026  
**Status:** Draft  

**Next Steps:**
1. Review PRD for completeness
2. Review current GCP infrastructure
3. Prioritize Phase 0 tasks
4. Begin implementation

---

**End of Document**

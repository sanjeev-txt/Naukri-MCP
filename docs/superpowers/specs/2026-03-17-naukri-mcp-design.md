# Naukri.com Local MCP Server — Design Spec
**Date:** 2026-03-17
**Status:** Approved
**Stack:** Python, Playwright, Claude API, SQLite

---

## Overview

A local MCP (Model Context Protocol) server that enables Claude to search, review, and apply to jobs on Naukri.com on behalf of the user. It uses AI-powered resume tailoring per job before applying, and tracks all applications in a local SQLite database.

> **Note:** Automated job applications via browser automation may violate Naukri's Terms of Service. This tool is intended for personal productivity use only. The user accepts this risk by proceeding.

---

## Goals

- Search Naukri.com for jobs using filters (title, location, experience, skills)
- Show found jobs to user for approval before applying
- Tailor resume per job using Claude API (combining master resume + Naukri profile data)
- Upload tailored resume to Naukri profile and submit application
- Track all job applications with full history in SQLite

---

## Architecture

```
naukri-mcp/
├── server.py                  # MCP server — exposes tools to Claude
├── naukri.py                  # Playwright browser controller (login, search, apply, profile fetch)
├── resume_tailor.py           # Claude API — tailors resume per job description
├── tracker.py                 # SQLite — logs all applied jobs
├── models.py                  # Shared data models (Job, JobDetail, ApplicationResult)
├── .env                       # Naukri credentials + Claude API key (never committed)
├── .gitignore                 # Protects .env, *.db, resume files, tailored resumes
├── resume_base.pdf            # User's master resume (never committed)
└── requirements.txt
```

### Data Flow

```
Claude → MCP Server → Naukri Browser (Playwright)
                    → Resume Tailor (Claude API)
                    → Job Tracker (SQLite)
```

---

## Security

### `.gitignore` (mandatory)
```
.env
*.db
resume_base.pdf
tailored_resumes/
.naukri_session/
```

### Session Cookie Storage
- Browser session cookies saved to `~/.naukri-mcp/session/` (user-owned, not world-readable)
- Directory created with `chmod 700` on first run
- Cookies reused across sessions to avoid repeated logins
- If cookies expire, browser re-authenticates automatically using `.env` credentials
- Cookies are never committed to git

### Tailored Resume Storage
- Tailored PDFs saved to `~/.naukri-mcp/resumes/` (configurable via `RESUME_OUTPUT_DIR` in `.env`)
- Directory created with `chmod 700` on first run
- Default is NOT `/tmp/` to avoid world-readable exposure of PII

---

## Components

### 1. MCP Server (`server.py`)
- Built with `mcp` Python SDK
- Exposes 6 tools to Claude (including `approve_job`)
- Orchestrates calls between browser, tailor, and tracker
- Enforces approval gate: `apply_job` checks status is `approved` before proceeding

### 2. Naukri Browser Controller (`naukri.py`)
- Uses `playwright` (async) for browser automation
- Handles: login, session management, job search, job detail extraction, profile data fetch, resume upload, application submission
- Credentials loaded from `.env`
- Supports headless and headed mode (via `HEADLESS` env var)
- Minimum 2-second delay between page loads to avoid rate limiting
- Maximum 50 job applications per session to reduce block risk

### 3. Resume Tailor (`resume_tailor.py`)
- Extracts text from master resume PDF (`pdfplumber`)
- Receives Naukri profile data (skills, experience, education) from `naukri.py`
- Sends master resume + profile data + job description to Claude API
- Claude returns tailored resume content optimized for the job
- Generates PDF using a predefined ATS-friendly template (`reportlab`)
- Saves to `~/.naukri-mcp/resumes/<job_id>_<timestamp>.pdf`

### 4. Job Tracker (`tracker.py`)
- SQLite database at `~/.naukri-mcp/jobs.db`
- Tracks full lifecycle of every discovered job

### 5. Data Models (`models.py`)
- Shared Pydantic models used across all components

---

## Data Models

```python
class Job(BaseModel):
    id: str                    # Naukri job ID
    title: str
    company: str
    location: str
    salary: str | None
    skills_required: list[str]
    url: str                   # Direct Naukri job URL
    status: str                # 'found' | 'approved' | 'applied' | 'skipped' | 'failed' | 'expired'
    found_at: datetime

class JobDetail(Job):
    description: str
    experience_required: str
    posted_at: str
    applicants: int | None

class ApplicationResult(BaseModel):
    job_id: str
    success: bool
    resume_used: str | None    # Path to tailored resume PDF, or None if fallback
    used_tailored_resume: bool
    error: str | None
    applied_at: datetime
```

---

## Database Schema

```sql
CREATE TABLE jobs (
    id              TEXT PRIMARY KEY,   -- Naukri job ID
    title           TEXT,
    company         TEXT,
    location        TEXT,
    salary          TEXT,
    description     TEXT,
    url             TEXT,               -- Direct job URL
    skills_required TEXT,               -- JSON array of skills
    status          TEXT,               -- 'found'|'approved'|'applied'|'skipped'|'failed'|'expired'
    found_at        DATETIME,           -- When job was discovered
    applied_at      DATETIME,           -- When application was submitted
    resume_used     TEXT,               -- Path to tailored resume PDF used
    error_message   TEXT                -- Error detail if status = 'failed'
);
```

---

## MCP Tools

### `search_jobs`
Search Naukri.com for jobs matching given criteria. Saves results with status `found`.

```python
search_jobs(
    title: str,
    location: str,
    experience: str,
    skills: list[str],
    max_results: int = 20
) -> list[Job]
```

### `get_job_details`
Fetch full job description and company info for a specific job.

```python
get_job_details(job_id: str) -> JobDetail
```

### `list_pending_jobs`
List all jobs with status `found` awaiting user approval.

```python
list_pending_jobs() -> list[Job]
```

### `approve_job`
Mark one or more jobs as approved for application. **Required before `apply_job`.**

```python
approve_job(job_ids: list[str]) -> list[Job]  # returns updated jobs
```

### `apply_job`
Tailor resume, upload to Naukri, and submit application. **Only works on jobs with status `approved`.**

- If `tailor_resume=True` and resume upload fails: pauses and asks user whether to proceed with existing profile or abort (no silent fallback)
- Supports `dry_run=True` to test full pipeline without submitting

```python
apply_job(
    job_id: str,
    tailor_resume: bool = True,
    dry_run: bool = False
) -> ApplicationResult
```

### `get_applied_jobs`
View history of applied jobs with optional filtering.

```python
get_applied_jobs(
    status: str | None = None,   # filter by status
    since_date: str | None = None,
    limit: int = 50
) -> list[Job]
```

---

## Configuration (`.env`)

```env
NAUKRI_EMAIL=your@email.com
NAUKRI_PASSWORD=yourpassword
CLAUDE_API_KEY=sk-ant-...
BASE_RESUME_PATH=./resume_base.pdf
RESUME_OUTPUT_DIR=~/.naukri-mcp/resumes
HEADLESS=true
REQUEST_DELAY_SECONDS=2
MAX_APPLICATIONS_PER_SESSION=50
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Login fails | Return error with reason, do not proceed |
| Already applied to job | Skip, mark as duplicate in tracker |
| Resume upload fails | Pause, ask user: proceed without tailored resume OR abort |
| Job no longer available | Mark as `expired` in tracker |
| Naukri CAPTCHA/block | Pause, notify user to handle manually, stop session |
| Claude API failure | Notify user, ask whether to apply without tailoring or abort |
| `apply_job` called on non-approved job | Return error: "Job must be approved before applying. Use `approve_job` first." |

---

## Naukri Profile Fetch (in `naukri.py`)

Before resume tailoring, the browser controller fetches the user's Naukri profile:
1. Navigate to `https://www.naukri.com/mnjuser/profile` (authenticated)
2. Extract: headline, skills, work experience entries, education entries
3. Return as structured `NaukriProfile` dict to `resume_tailor.py`
4. Reuses existing authenticated browser session — no separate login needed

---

## Rate Limiting Strategy

- Minimum `REQUEST_DELAY_SECONDS` (default: 2s) between every page load
- Random jitter of 0-1s added to each delay to appear more human
- Maximum `MAX_APPLICATIONS_PER_SESSION` (default: 50) applications before stopping
- If Naukri returns a CAPTCHA or 429, session is paused and user is notified

---

## Example Usage

```
User: Search Python developer jobs in Bangalore, 3-5 years experience

Claude: Found 15 jobs. Here's the list... [titles, companies, salaries]
        Which ones should I apply to?

User: Approve jobs 1, 3, and 7

Claude: Jobs 1, 3, 7 marked as approved.

User: Apply to approved jobs

Claude: Tailoring resume for job 1 (Flipkart - Senior Python Dev)... done
        Uploading resume... done. Applying... Applied!

        Tailoring resume for job 3 (Swiggy - Backend Engineer)... done
        Uploading resume... done. Applying... Applied!

        Tailoring resume for job 7 (Zomato - Python Engineer)... done
        Uploading resume... done. Applying... Applied!

        3/3 applications submitted. All logged to tracker.
```

---

## Dependencies

```
mcp              # MCP Python SDK
playwright       # Browser automation
anthropic        # Claude API for resume tailoring
pdfplumber       # Extract text from master resume PDF
reportlab        # Generate tailored resume PDFs (ATS-friendly template)
pydantic         # Data models
python-dotenv    # Load .env config
aiosqlite        # Async SQLite for job tracker
```

---

## Out of Scope (v1)

- LinkedIn / Indeed integration (Naukri only)
- Cover letter generation (resume tailoring only)
- Email notifications
- Dashboard UI
- Resume template customization

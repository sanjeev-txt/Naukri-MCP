# Naukri MCP Server Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python MCP server that lets Claude search, approve, and apply to Naukri.com jobs with AI-tailored resumes.

**Architecture:** Playwright controls a browser to interact with Naukri.com. Claude API tailors the resume per job. SQLite tracks all applications. An MCP server exposes 6 tools to Claude.

**Tech Stack:** Python 3.11+, `mcp` SDK, `playwright`, `anthropic`, `pdfplumber`, `reportlab`, `pydantic`, `aiosqlite`, `python-dotenv`

---

## Chunk 1: Project Scaffolding

### Task 1: Initialize project structure

**Files:**
- Create: `naukri-mcp/.gitignore`
- Create: `naukri-mcp/.env.example`
- Create: `naukri-mcp/requirements.txt`
- Create: `naukri-mcp/pytest.ini`
- Create: `naukri-mcp/tests/__init__.py`

- [ ] **Step 1: Enter project root**

```bash
cd /Users/primathon/Downloads/naukri-mcp
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
*.db
resume_base.pdf
tailored_resumes/
.naukri_session/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.venv/
```

- [ ] **Step 3: Create `.env.example`**

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

- [ ] **Step 4: Create `requirements.txt`**

```
mcp>=1.0.0
playwright>=1.40.0
anthropic>=0.40.0
pdfplumber>=0.10.0
reportlab>=4.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
aiosqlite>=0.20.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 5: Create `pytest.ini`** (required for pytest-asyncio to work)

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 6: Create `tests/__init__.py`** (empty file)

- [ ] **Step 7: Create virtual environment and install deps**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Expected: All packages installed, chromium browser downloaded.

- [ ] **Step 8: Commit**

```bash
git init
git add .gitignore .env.example requirements.txt pytest.ini tests/__init__.py
git commit -m "chore: scaffold naukri-mcp project"
```

---

## Chunk 2: Data Models

### Task 2: Shared Pydantic models

**Files:**
- Create: `naukri-mcp/models.py`
- Create: `naukri-mcp/tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_models.py`:

```python
from datetime import datetime
import pytest
from models import Job, JobDetail, ApplicationResult, NaukriProfile


def test_job_model_defaults():
    job = Job(
        id="J001",
        title="Python Developer",
        company="Flipkart",
        location="Bangalore",
        skills_required=["Python", "Django"],
        url="https://www.naukri.com/job/J001",
        found_at=datetime.now(),
    )
    assert job.status == "found"
    assert job.salary is None
    assert job.applied_at is None
    assert job.resume_used is None
    assert job.error_message is None


def test_job_status_values():
    valid_statuses = ["found", "approved", "applied", "skipped", "failed", "expired"]
    for status in valid_statuses:
        job = Job(
            id="J001", title="Dev", company="Co", location="City",
            skills_required=[], url="http://x.com", found_at=datetime.now(),
            status=status
        )
        assert job.status == status


def test_job_detail_inherits_job():
    detail = JobDetail(
        id="J002", title="Dev", company="Co", location="City",
        skills_required=["Python"], url="http://x.com", found_at=datetime.now(),
        description="Full stack developer role",
        experience_required="3-5 years",
        posted_at="2 days ago",
    )
    assert detail.status == "found"
    assert detail.description == "Full stack developer role"
    assert detail.applicants is None


def test_application_result_success():
    result = ApplicationResult(
        job_id="J001",
        success=True,
        resume_used="/home/user/.naukri-mcp/resumes/J001.pdf",
        used_tailored_resume=True,
        error=None,
        applied_at=datetime.now(),
    )
    assert result.success is True
    assert result.error is None


def test_application_result_failure():
    result = ApplicationResult(
        job_id="J001",
        success=False,
        resume_used=None,
        used_tailored_resume=False,
        error="CAPTCHA detected",
        applied_at=datetime.now(),
    )
    assert result.success is False
    assert result.resume_used is None


def test_naukri_profile_model():
    profile = NaukriProfile(
        headline="Senior Python Developer",
        skills=["Python", "Django", "FastAPI"],
        experience=[{"company": "Flipkart", "role": "Engineer", "duration": "2 years"}],
        education=[{"degree": "B.Tech", "institution": "IIT Delhi", "year": "2018"}],
    )
    assert profile.headline == "Senior Python Developer"
    assert len(profile.skills) == 3


def test_job_extra_fields_settable():
    """applied_at, resume_used, error_message are optional fields on Job."""
    from datetime import datetime as dt
    job = Job(
        id="J003", title="Dev", company="Co", location="City",
        skills_required=[], url="http://x.com", found_at=dt.now(),
        status="applied",
        applied_at=dt.now(),
        resume_used="/path/to/resume.pdf",
    )
    assert job.applied_at is not None
    assert job.resume_used == "/path/to/resume.pdf"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/primathon/Downloads/naukri-mcp
source .venv/bin/activate
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: Implement `models.py`**

```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class Job(BaseModel):
    id: str
    title: str
    company: str
    location: str
    salary: str | None = None
    skills_required: list[str] = Field(default_factory=list)
    url: str
    status: str = "found"
    found_at: datetime
    # Populated after application lifecycle events
    applied_at: datetime | None = None
    resume_used: str | None = None
    error_message: str | None = None


class JobDetail(Job):
    description: str
    experience_required: str
    posted_at: str
    applicants: int | None = None


class ApplicationResult(BaseModel):
    job_id: str
    success: bool
    resume_used: str | None
    used_tailored_resume: bool
    error: str | None
    applied_at: datetime


class NaukriProfile(BaseModel):
    headline: str
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
pytest tests/test_models.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add shared pydantic data models"
```

---

## Chunk 3: Job Tracker

### Task 3: SQLite job tracker

**Files:**
- Create: `naukri-mcp/tracker.py`
- Create: `naukri-mcp/tests/test_tracker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tracker.py`:

```python
import asyncio
from datetime import datetime
import pytest
import pytest_asyncio
from models import Job
from tracker import JobTracker


@pytest_asyncio.fixture
async def tracker(tmp_path):
    db_path = str(tmp_path / "test_jobs.db")
    t = JobTracker(db_path=db_path)
    await t.init()
    yield t
    await t.close()


async def test_save_and_get_job(tracker):
    job = Job(
        id="J001", title="Python Dev", company="Flipkart",
        location="Bangalore", skills_required=["Python"],
        url="https://naukri.com/job/J001", found_at=datetime.now()
    )
    await tracker.save_job(job)
    result = await tracker.get_job("J001")
    assert result is not None
    assert result.title == "Python Dev"
    assert result.status == "found"


async def test_update_job_status(tracker):
    job = Job(
        id="J002", title="Django Dev", company="Swiggy",
        location="Mumbai", skills_required=["Django"],
        url="https://naukri.com/job/J002", found_at=datetime.now()
    )
    await tracker.save_job(job)
    await tracker.update_status("J002", "approved")
    result = await tracker.get_job("J002")
    assert result.status == "approved"


async def test_list_jobs_by_status(tracker):
    for i, status in enumerate(["found", "found", "approved"]):
        job = Job(
            id=f"J00{i}", title=f"Dev {i}", company="Co",
            location="City", skills_required=[],
            url=f"https://naukri.com/job/J00{i}", found_at=datetime.now(),
            status=status
        )
        await tracker.save_job(job)

    found_jobs = await tracker.list_jobs(status="found")
    assert len(found_jobs) == 2

    approved_jobs = await tracker.list_jobs(status="approved")
    assert len(approved_jobs) == 1


async def test_mark_applied(tracker):
    job = Job(
        id="J010", title="Dev", company="Co", location="City",
        skills_required=[], url="https://naukri.com/job/J010",
        found_at=datetime.now(), status="approved"
    )
    await tracker.save_job(job)
    await tracker.mark_applied("J010", resume_used="/path/to/resume.pdf")
    result = await tracker.get_job("J010")
    assert result.status == "applied"
    assert result.resume_used == "/path/to/resume.pdf"
    assert result.applied_at is not None


async def test_mark_failed(tracker):
    job = Job(
        id="J011", title="Dev", company="Co", location="City",
        skills_required=[], url="https://naukri.com/job/J011",
        found_at=datetime.now(), status="approved"
    )
    await tracker.save_job(job)
    await tracker.mark_failed("J011", error="CAPTCHA detected")
    result = await tracker.get_job("J011")
    assert result.status == "failed"
    assert result.error_message == "CAPTCHA detected"


async def test_duplicate_job_skipped(tracker):
    job = Job(
        id="J020", title="Dev", company="Co", location="City",
        skills_required=[], url="https://naukri.com/job/J020",
        found_at=datetime.now(), status="applied"
    )
    await tracker.save_job(job)
    is_duplicate = await tracker.is_duplicate("J020")
    assert is_duplicate is True

    not_dup = await tracker.is_duplicate("J999")
    assert not_dup is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_tracker.py -v
```

Expected: `ModuleNotFoundError: No module named 'tracker'`

- [ ] **Step 3: Implement `tracker.py`**

```python
import json
from datetime import datetime
from pathlib import Path
import aiosqlite
from models import Job


class JobTracker:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            data_dir = Path.home() / ".naukri-mcp"
            data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            db_path = str(data_dir / "jobs.db")
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id              TEXT PRIMARY KEY,
                title           TEXT,
                company         TEXT,
                location        TEXT,
                salary          TEXT,
                description     TEXT,
                url             TEXT,
                skills_required TEXT,
                status          TEXT DEFAULT 'found',
                found_at        DATETIME,
                applied_at      DATETIME,
                resume_used     TEXT,
                error_message   TEXT
            )
        """)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def save_job(self, job: Job):
        await self._conn.execute("""
            INSERT OR IGNORE INTO jobs
                (id, title, company, location, salary, url, skills_required, status, found_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.id, job.title, job.company, job.location, job.salary,
            job.url, json.dumps(job.skills_required), job.status,
            job.found_at.isoformat()
        ))
        await self._conn.commit()

    async def get_job(self, job_id: str) -> Job | None:
        async with self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    async def update_status(self, job_id: str, status: str):
        await self._conn.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)
        )
        await self._conn.commit()

    async def list_jobs(
        self,
        status: str | None = None,
        since_date: str | None = None,
        limit: int = 50,
    ) -> list[Job]:
        query = "SELECT * FROM jobs WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if since_date:
            query += " AND found_at >= ?"
            params.append(since_date)
        query += " ORDER BY found_at DESC LIMIT ?"
        params.append(limit)

        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_job(r) for r in rows]

    async def mark_applied(self, job_id: str, resume_used: str | None):
        await self._conn.execute("""
            UPDATE jobs SET status = 'applied', applied_at = ?, resume_used = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), resume_used, job_id))
        await self._conn.commit()

    async def mark_failed(self, job_id: str, error: str):
        await self._conn.execute("""
            UPDATE jobs SET status = 'failed', error_message = ? WHERE id = ?
        """, (error, job_id))
        await self._conn.commit()

    async def is_duplicate(self, job_id: str) -> bool:
        # Only jobs with status='applied' are considered duplicates.
        # Failed/skipped jobs can be retried.
        async with self._conn.execute(
            "SELECT id FROM jobs WHERE id = ? AND status = 'applied'", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    def _row_to_job(self, row) -> Job:
        data = dict(row)
        data["skills_required"] = json.loads(data["skills_required"] or "[]")
        data["found_at"] = datetime.fromisoformat(data["found_at"])
        if data.get("applied_at"):
            data["applied_at"] = datetime.fromisoformat(data["applied_at"])
        return Job(
            id=data["id"],
            title=data["title"],
            company=data["company"],
            location=data["location"],
            salary=data["salary"],
            skills_required=data["skills_required"],
            url=data["url"],
            status=data["status"],
            found_at=data["found_at"],
            applied_at=data.get("applied_at"),
            resume_used=data.get("resume_used"),
            error_message=data.get("error_message"),
        )
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
pytest tests/test_tracker.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tracker.py tests/test_tracker.py
git commit -m "feat: add SQLite job tracker"
```

---

## Chunk 4: Naukri Browser Controller

### Task 4: Login, session management, and rate limiting

**Files:**
- Create: `naukri-mcp/naukri.py`
- Create: `naukri-mcp/tests/test_naukri_login.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_naukri_login.py`:

```python
import time
import stat
import pytest
from naukri import NaukriBrowser


async def test_delay_is_applied():
    """Verify that _delay() waits at least the configured minimum."""
    browser = NaukriBrowser(email="x@x.com", password="pass", delay_seconds=0.1)
    start = time.monotonic()
    await browser._delay()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.1


def test_session_dir_created_with_correct_permissions():
    """Verify session dir exists at ~/.naukri-mcp/session with mode 700."""
    browser = NaukriBrowser(email="x@x.com", password="pass")
    session_dir = browser.session_dir
    assert session_dir.exists()
    mode = oct(stat.S_IMODE(session_dir.stat().st_mode))
    assert mode == "0o700"


def test_resume_dir_created_with_correct_permissions(tmp_path):
    """Verify resume output dir is created with mode 700."""
    resume_dir = tmp_path / "resumes"
    browser = NaukriBrowser(
        email="x@x.com", password="pass",
        resume_output_dir=str(resume_dir)
    )
    browser._ensure_dirs()
    assert resume_dir.exists()
    mode = oct(stat.S_IMODE(resume_dir.stat().st_mode))
    assert mode == "0o700"
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_naukri_login.py -v
```

Expected: `ModuleNotFoundError: No module named 'naukri'`

- [ ] **Step 3: Implement `naukri.py`**

```python
import asyncio
import os
import random
import stat
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from models import Job, JobDetail, NaukriProfile

load_dotenv()

NAUKRI_BASE = "https://www.naukri.com"
LOGIN_URL = f"{NAUKRI_BASE}/nlogin/login"
PROFILE_URL = f"{NAUKRI_BASE}/mnjuser/profile"


class NaukriError(Exception):
    pass


class CaptchaError(NaukriError):
    pass


class LoginError(NaukriError):
    pass


class NaukriBrowser:
    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        headless: bool = True,
        delay_seconds: float = 2.0,
        max_applications: int = 50,
        resume_output_dir: str | None = None,
    ):
        self.email = email or os.getenv("NAUKRI_EMAIL", "")
        self.password = password or os.getenv("NAUKRI_PASSWORD", "")
        self.headless = headless
        self.delay_seconds = delay_seconds
        self.max_applications = max_applications

        self.session_dir = Path.home() / ".naukri-mcp" / "session"
        self.resume_output_dir = Path(
            resume_output_dir or os.path.expanduser(
                os.getenv("RESUME_OUTPUT_DIR", "~/.naukri-mcp/resumes")
            )
        )
        self._ensure_dirs()

        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._applications_this_session = 0

    def _ensure_dirs(self):
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_dir.chmod(0o700)
        self.resume_output_dir.mkdir(parents=True, exist_ok=True)
        self.resume_output_dir.chmod(0o700)

    async def _delay(self):
        jitter = random.uniform(0, 1)
        await asyncio.sleep(self.delay_seconds + jitter)

    async def start(self):
        self._playwright = await async_playwright().start()
        storage_state = self.session_dir / "state.json"
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        if storage_state.exists():
            self._context = await self._browser.new_context(
                storage_state=str(storage_state)
            )
        else:
            self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

    async def stop(self):
        if self._context:
            storage_state = self.session_dir / "state.json"
            await self._context.storage_state(path=str(storage_state))
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _is_logged_in(self) -> bool:
        try:
            await self._page.goto(PROFILE_URL, wait_until="domcontentloaded")
            await self._delay()
            return "login" not in self._page.url
        except Exception:
            return False

    async def login(self):
        if await self._is_logged_in():
            return
        await self._page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await self._delay()
        await self._page.fill('input[placeholder*="Email"]', self.email)
        await self._page.fill('input[placeholder*="Password"]', self.password)
        await self._page.click('button[type="submit"]')
        await self._delay()
        if "login" in self._page.url:
            raise LoginError("Login failed — check credentials or CAPTCHA")
        storage_state = self.session_dir / "state.json"
        await self._context.storage_state(path=str(storage_state))

    async def _check_captcha(self):
        # NOTE: URL-based CAPTCHA detection is a simplification.
        # Naukri can show a CAPTCHA without changing the URL.
        # If CAPTCHA detection is unreliable, check page title or content too.
        if "captcha" in self._page.url.lower():
            raise CaptchaError("Naukri is showing a CAPTCHA. Please handle manually.")
        title = await self._page.title()
        if "captcha" in title.lower() or "robot" in title.lower():
            raise CaptchaError("Naukri CAPTCHA detected in page title.")

    async def search_jobs(
        self,
        title: str,
        location: str,
        experience: str,
        skills: list[str],
        max_results: int = 20,
    ) -> list[Job]:
        await self.login()
        keyword = "-".join(title.lower().split())
        loc = "-".join(location.lower().split())
        url = f"{NAUKRI_BASE}/{keyword}-jobs-in-{loc}"
        await self._page.goto(url, wait_until="domcontentloaded")
        await self._delay()
        await self._check_captcha()
        jobs = []
        articles = await self._page.query_selector_all("article.jobTuple")
        for article in articles[:max_results]:
            job = await self._parse_job_card(article)
            if job:
                jobs.append(job)
        return jobs

    async def _parse_job_card(self, article) -> Job | None:
        try:
            from datetime import datetime
            title_el = await article.query_selector("a.title")
            company_el = await article.query_selector("a.subTitle")
            location_el = await article.query_selector("li.fleft.grey-text")
            salary_el = await article.query_selector("li.salary")
            skills_els = await article.query_selector_all("li.tag")
            href = await title_el.get_attribute("href") if title_el else ""
            job_id = href.rstrip("/").split("/")[-1] if href else ""
            return Job(
                id=job_id,
                title=await title_el.inner_text() if title_el else "",
                company=await company_el.inner_text() if company_el else "",
                location=await location_el.inner_text() if location_el else "",
                salary=await salary_el.inner_text() if salary_el else None,
                skills_required=[await s.inner_text() for s in skills_els],
                url=href or "",
                found_at=datetime.now(),
            )
        except Exception:
            return None

    async def get_job_details(self, job_id: str, url: str) -> JobDetail | None:
        await self.login()
        await self._page.goto(url, wait_until="domcontentloaded")
        await self._delay()
        await self._check_captcha()
        try:
            from datetime import datetime
            title = await self._page.inner_text("h1.jd-header-title")
            company = await self._page.inner_text("a.jd-header-comp-name")
            location = await self._page.inner_text("span.location")
            salary_el = await self._page.query_selector("span.salary")
            salary = await salary_el.inner_text() if salary_el else None
            description = await self._page.inner_text("div.job-desc")
            exp_el = await self._page.query_selector("span.exp")
            experience = await exp_el.inner_text() if exp_el else ""
            posted_el = await self._page.query_selector("span.posted-date")
            posted = await posted_el.inner_text() if posted_el else ""
            skill_els = await self._page.query_selector_all("span.tag-li")
            skills = [await s.inner_text() for s in skill_els]
            return JobDetail(
                id=job_id, title=title, company=company, location=location,
                salary=salary, skills_required=skills, url=url,
                description=description, experience_required=experience,
                posted_at=posted, found_at=datetime.now(),
            )
        except Exception:
            return None

    async def get_profile(self) -> NaukriProfile:
        await self.login()
        await self._page.goto(PROFILE_URL, wait_until="domcontentloaded")
        await self._delay()
        headline_el = await self._page.query_selector("div.headline")
        headline = await headline_el.inner_text() if headline_el else ""
        skill_els = await self._page.query_selector_all("span.chip")
        skills = [await s.inner_text() for s in skill_els]
        return NaukriProfile(headline=headline, skills=skills)

    async def upload_resume(self, resume_path: str) -> bool:
        await self.login()
        await self._page.goto(PROFILE_URL, wait_until="domcontentloaded")
        await self._delay()
        try:
            upload_input = await self._page.query_selector("input[type='file']")
            if upload_input:
                await upload_input.set_input_files(resume_path)
                await self._delay()
                save_btn = await self._page.query_selector("button.save-resume")
                if save_btn:
                    await save_btn.click()
                    await self._delay()
            return True
        except Exception:
            return False

    async def apply_to_job(self, url: str, dry_run: bool = False) -> bool:
        if self._applications_this_session >= self.max_applications:
            raise NaukriError(
                f"Max applications per session ({self.max_applications}) reached."
            )
        await self.login()
        await self._page.goto(url, wait_until="domcontentloaded")
        await self._delay()
        await self._check_captcha()
        if dry_run:
            apply_btn = await self._page.query_selector("button.apply-button")
            return apply_btn is not None
        try:
            apply_btn = await self._page.query_selector("button.apply-button")
            if not apply_btn:
                return False
            await apply_btn.click()
            await self._delay()
            self._applications_this_session += 1
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_naukri_login.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add naukri.py tests/test_naukri_login.py
git commit -m "feat: add naukri browser controller with login and rate limiting"
```

---

## Chunk 5: Resume Tailor

### Task 5: AI-powered resume tailoring

**Files:**
- Create: `naukri-mcp/resume_tailor.py`
- Create: `naukri-mcp/tests/test_resume_tailor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_resume_tailor.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from models import NaukriProfile


@pytest.fixture
def sample_profile():
    return NaukriProfile(
        headline="Senior Python Developer",
        skills=["Python", "Django", "FastAPI", "PostgreSQL"],
        experience=[{"company": "Flipkart", "role": "Backend Engineer", "duration": "3 years"}],
        education=[{"degree": "B.Tech CS", "institution": "IIT Delhi", "year": "2018"}],
    )


@pytest.fixture
def sample_jd():
    return "We are looking for a Python Developer with 3-5 years experience. Required: Python, FastAPI, PostgreSQL."


async def test_tailor_returns_string(tmp_path, sample_profile, sample_jd):
    """tailor_resume returns non-empty tailored text."""
    from resume_tailor import ResumeTailor

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Tailored resume content here")]
    mock_client.messages.create = MagicMock(return_value=mock_msg)

    tailor = ResumeTailor(client=mock_client)
    result = await tailor.tailor_resume(
        master_resume_text="John Doe\nPython Developer with 4 years experience.",
        profile=sample_profile,
        job_description=sample_jd,
    )
    assert isinstance(result, str)
    assert len(result) > 0


async def test_generate_pdf_creates_file(tmp_path, sample_profile, sample_jd):
    """generate_pdf saves a PDF file to the output directory."""
    from resume_tailor import ResumeTailor

    mock_client = MagicMock()
    tailor = ResumeTailor(client=mock_client, output_dir=str(tmp_path))
    pdf_path = await tailor.generate_pdf(
        tailored_text="John Doe\nSenior Python Developer\n\nSkills: Python, FastAPI",
        job_id="J001",
    )
    assert Path(pdf_path).exists()
    assert pdf_path.endswith(".pdf")


async def test_extract_text_from_pdf(tmp_path):
    """extract_text reads text from a PDF file."""
    from reportlab.pdfgen import canvas
    from resume_tailor import ResumeTailor

    pdf_path = str(tmp_path / "test.pdf")
    c = canvas.Canvas(pdf_path)
    c.drawString(100, 750, "Hello PDF World")
    c.save()

    mock_client = MagicMock()
    tailor = ResumeTailor(client=mock_client)
    text = tailor.extract_text(pdf_path)
    # pdfplumber should extract the text we embedded
    assert "Hello" in text
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_resume_tailor.py -v
```

Expected: `ModuleNotFoundError: No module named 'resume_tailor'`

- [ ] **Step 3: Implement `resume_tailor.py`**

Note: `tailor_resume` uses `asyncio.to_thread` to avoid blocking the event loop with the synchronous Anthropic SDK call.

```python
import asyncio
import os
from datetime import datetime
from pathlib import Path

import anthropic
import pdfplumber
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from models import NaukriProfile

load_dotenv()

TAILOR_PROMPT = """You are an expert resume writer. Given a candidate's master resume, their Naukri profile, and a job description, produce a tailored resume in plain text format.

Rules:
- Keep all information truthful — do not invent experience or skills
- Highlight skills and experience that match the job description
- Use ATS-friendly formatting: clear section headers, bullet points with "-"
- Sections: Summary, Skills, Experience, Education
- Be concise — target 1 page worth of content

Master Resume:
{master_resume}

Naukri Profile:
Headline: {headline}
Skills: {skills}
Experience: {experience}
Education: {education}

Job Description:
{job_description}

Return ONLY the tailored resume text. No preamble, no explanation."""


class ResumeTailor:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        output_dir: str | None = None,
    ):
        self._client = client or anthropic.Anthropic(
            api_key=os.getenv("CLAUDE_API_KEY")
        )
        self.output_dir = Path(
            output_dir or os.path.expanduser(
                os.getenv("RESUME_OUTPUT_DIR", "~/.naukri-mcp/resumes")
            )
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.chmod(0o700)

    def extract_text(self, pdf_path: str) -> str:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)

    async def tailor_resume(
        self,
        master_resume_text: str,
        profile: NaukriProfile,
        job_description: str,
    ) -> str:
        prompt = TAILOR_PROMPT.format(
            master_resume=master_resume_text,
            headline=profile.headline,
            skills=", ".join(profile.skills),
            experience=str(profile.experience),
            education=str(profile.education),
            job_description=job_description,
        )
        # Use asyncio.to_thread to avoid blocking the event loop with the
        # synchronous Anthropic SDK call.
        message = await asyncio.to_thread(
            self._client.messages.create,
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def generate_pdf(self, tailored_text: str, job_id: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{job_id}_{timestamp}.pdf"
        output_path = str(self.output_dir / filename)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"], fontSize=10, leading=14
        )
        story = []
        for line in tailored_text.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.2 * cm))
            else:
                story.append(Paragraph(line, body_style))

        doc.build(story)
        return output_path

    async def create_tailored_resume(
        self,
        master_resume_path: str,
        profile: NaukriProfile,
        job_description: str,
        job_id: str,
    ) -> str:
        master_text = self.extract_text(master_resume_path)
        tailored_text = await self.tailor_resume(master_text, profile, job_description)
        return await self.generate_pdf(tailored_text, job_id)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_resume_tailor.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add resume_tailor.py tests/test_resume_tailor.py
git commit -m "feat: add AI resume tailor with PDF generation"
```

---

## Chunk 6: MCP Server

### Task 6: MCP server with all 6 tools

**Files:**
- Create: `naukri-mcp/server.py`
- Create: `naukri-mcp/tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_server.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from models import Job


def make_job(job_id="J001", status="found"):
    return Job(
        id=job_id, title="Python Dev", company="Flipkart",
        location="Bangalore", skills_required=["Python"],
        url=f"https://naukri.com/job/{job_id}", found_at=datetime.now(),
        status=status
    )


async def test_search_jobs_saves_to_tracker():
    from server import NaukriMCPServer
    server = NaukriMCPServer.__new__(NaukriMCPServer)
    server.tracker = AsyncMock()
    server.browser = AsyncMock()
    server.browser.search_jobs = AsyncMock(return_value=[make_job()])

    result = await server._search_jobs("Python Dev", "Bangalore", "3-5", ["Python"], 10)
    server.tracker.save_job.assert_called_once()
    assert len(result) == 1


async def test_approve_job_updates_status():
    from server import NaukriMCPServer
    server = NaukriMCPServer.__new__(NaukriMCPServer)
    server.tracker = AsyncMock()
    server.tracker.get_job = AsyncMock(return_value=make_job("J001", "found"))

    await server._approve_jobs(["J001"])
    server.tracker.update_status.assert_called_with("J001", "approved")


async def test_apply_job_rejects_non_approved():
    from server import NaukriMCPServer
    server = NaukriMCPServer.__new__(NaukriMCPServer)
    server.tracker = AsyncMock()
    server.tracker.get_job = AsyncMock(return_value=make_job("J001", "found"))

    result = await server._apply_job("J001", tailor_resume=False, dry_run=False)
    assert result["success"] is False
    assert "approve" in result["error"].lower()


async def test_apply_job_checks_duplicate():
    from server import NaukriMCPServer
    server = NaukriMCPServer.__new__(NaukriMCPServer)
    server.tracker = AsyncMock()
    server.tracker.get_job = AsyncMock(return_value=make_job("J001", "approved"))
    server.tracker.is_duplicate = AsyncMock(return_value=True)

    result = await server._apply_job("J001", tailor_resume=False, dry_run=False)
    assert result["success"] is False
    assert "already applied" in result["error"].lower()


async def test_list_pending_jobs_returns_found():
    from server import NaukriMCPServer
    server = NaukriMCPServer.__new__(NaukriMCPServer)
    server.tracker = AsyncMock()
    server.tracker.list_jobs = AsyncMock(return_value=[make_job()])

    result = await server._list_pending_jobs()
    server.tracker.list_jobs.assert_called_with(status="found")
    assert len(result) == 1


async def test_apply_job_captcha_marks_failed():
    """CaptchaError must mark the job as failed and return error — not be swallowed."""
    from server import NaukriMCPServer
    from naukri import CaptchaError
    server = NaukriMCPServer.__new__(NaukriMCPServer)
    server.tracker = AsyncMock()
    server.tracker.get_job = AsyncMock(return_value=make_job("J001", "approved"))
    server.tracker.is_duplicate = AsyncMock(return_value=False)
    server.browser = AsyncMock()
    server.browser.apply_to_job = AsyncMock(side_effect=CaptchaError("CAPTCHA!"))
    server.tailor = AsyncMock()
    server.base_resume_path = "./resume_base.pdf"

    result = await server._apply_job("J001", tailor_resume=False, dry_run=False)
    assert result["success"] is False
    assert "CAPTCHA" in result["error"]
    server.tracker.mark_failed.assert_called_once_with("J001", "CAPTCHA!")
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_server.py -v
```

Expected: `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Implement `server.py`**

```python
import asyncio
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from models import Job, ApplicationResult
from naukri import NaukriBrowser, NaukriError, CaptchaError, LoginError
from resume_tailor import ResumeTailor
from tracker import JobTracker

load_dotenv()

app = Server("naukri-mcp")


class NaukriMCPServer:
    def __init__(self):
        self.tracker = JobTracker()
        self.browser = NaukriBrowser(
            headless=os.getenv("HEADLESS", "true").lower() == "true",
            delay_seconds=float(os.getenv("REQUEST_DELAY_SECONDS", "2")),
            max_applications=int(os.getenv("MAX_APPLICATIONS_PER_SESSION", "50")),
        )
        self.tailor = ResumeTailor()
        self.base_resume_path = os.getenv("BASE_RESUME_PATH", "./resume_base.pdf")
        self._started = False

    async def start(self):
        await self.tracker.init()
        await self.browser.start()
        self._started = True

    async def stop(self):
        await self.browser.stop()
        await self.tracker.close()

    async def _search_jobs(
        self, title: str, location: str, experience: str,
        skills: list[str], max_results: int
    ) -> list[dict]:
        jobs = await self.browser.search_jobs(title, location, experience, skills, max_results)
        for job in jobs:
            await self.tracker.save_job(job)
        return [j.model_dump(mode="json") for j in jobs]

    async def _get_job_details(self, job_id: str) -> dict:
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found in tracker"}
        detail = await self.browser.get_job_details(job_id, job.url)
        if not detail:
            return {"error": f"Could not fetch details for job {job_id}"}
        return detail.model_dump(mode="json")

    async def _list_pending_jobs(self) -> list[dict]:
        jobs = await self.tracker.list_jobs(status="found")
        return [j.model_dump(mode="json") for j in jobs]

    async def _approve_jobs(self, job_ids: list[str]) -> list[dict]:
        updated = []
        for job_id in job_ids:
            job = await self.tracker.get_job(job_id)
            if job:
                await self.tracker.update_status(job_id, "approved")
                job.status = "approved"
                updated.append(job.model_dump(mode="json"))
        return updated

    async def _apply_job(
        self, job_id: str, tailor_resume: bool, dry_run: bool
    ) -> dict:
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"success": False, "error": f"Job {job_id} not found"}

        if job.status != "approved":
            return {
                "success": False,
                "error": "Job must be approved before applying. Use approve_job first.",
            }

        if await self.tracker.is_duplicate(job_id):
            return {"success": False, "error": f"Already applied to job {job_id}"}

        resume_path = None
        used_tailored = False

        if tailor_resume:
            try:
                profile = await self.browser.get_profile()
                detail = await self.browser.get_job_details(job_id, job.url)
                jd = detail.description if detail else job.title
                resume_path = await self.tailor.create_tailored_resume(
                    self.base_resume_path, profile, jd, job_id
                )
                uploaded = await self.browser.upload_resume(resume_path)
                if not uploaded:
                    return {
                        "success": False,
                        "error": (
                            "Resume upload failed. Either retry with tailor_resume=False "
                            "to apply with your existing Naukri profile resume, or abort."
                        ),
                        "resume_path": resume_path,
                    }
                used_tailored = True
            except (CaptchaError, LoginError) as e:
                # Surface these immediately — do not fall back silently
                await self.tracker.mark_failed(job_id, str(e))
                return {"success": False, "error": str(e)}
            except Exception as e:
                return {
                    "success": False,
                    "error": (
                        f"Resume tailoring failed: {str(e)}. "
                        "Retry with tailor_resume=False to apply without tailoring."
                    ),
                }

        try:
            success = await self.browser.apply_to_job(job.url, dry_run=dry_run)
        except CaptchaError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}
        except NaukriError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}

        if not dry_run and success:
            await self.tracker.mark_applied(job_id, resume_path)

        return ApplicationResult(
            job_id=job_id,
            success=success,
            resume_used=resume_path,
            used_tailored_resume=used_tailored,
            error=None if success else "Application button not found",
            applied_at=datetime.now(),
        ).model_dump(mode="json")

    async def _get_applied_jobs(
        self, status: str | None, since_date: str | None, limit: int
    ) -> list[dict]:
        jobs = await self.tracker.list_jobs(status=status, since_date=since_date, limit=limit)
        return [j.model_dump(mode="json") for j in jobs]


_server_instance: NaukriMCPServer | None = None


def get_server() -> NaukriMCPServer:
    global _server_instance
    if _server_instance is None:
        _server_instance = NaukriMCPServer()
    return _server_instance


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_jobs",
            description="Search Naukri.com for jobs matching title, location, experience, and skills",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Job title e.g. Python Developer"},
                    "location": {"type": "string", "description": "City e.g. Bangalore"},
                    "experience": {"type": "string", "description": "e.g. 3-5 years"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["title", "location", "experience"],
            },
        ),
        types.Tool(
            name="get_job_details",
            description="Get full description and details of a specific job by ID",
            inputSchema={
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="list_pending_jobs",
            description="List all jobs found but not yet approved or applied to",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="approve_job",
            description="Approve one or more jobs for application. Must be called before apply_job.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["job_ids"],
            },
        ),
        types.Tool(
            name="apply_job",
            description="Apply to an approved job. Tailors resume via Claude API, uploads to Naukri, and submits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "tailor_resume": {"type": "boolean", "default": True, "description": "Use Claude to tailor resume for this job"},
                    "dry_run": {"type": "boolean", "default": False, "description": "Test full pipeline without actually submitting"},
                },
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="get_applied_jobs",
            description="View history of applied jobs with optional status/date filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status: found|approved|applied|failed|skipped|expired"},
                    "since_date": {"type": "string", "description": "ISO date string e.g. 2026-01-01"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    s = get_server()
    # Ensure initialized (guards against calling outside of main())
    if not s._started:
        await s.start()

    if name == "search_jobs":
        result = await s._search_jobs(
            arguments["title"], arguments["location"],
            arguments.get("experience", ""), arguments.get("skills", []),
            arguments.get("max_results", 20),
        )
    elif name == "get_job_details":
        result = await s._get_job_details(arguments["job_id"])
    elif name == "list_pending_jobs":
        result = await s._list_pending_jobs()
    elif name == "approve_job":
        result = await s._approve_jobs(arguments["job_ids"])
    elif name == "apply_job":
        result = await s._apply_job(
            arguments["job_id"],
            arguments.get("tailor_resume", True),
            arguments.get("dry_run", False),
        )
    elif name == "get_applied_jobs":
        result = await s._get_applied_jobs(
            arguments.get("status"), arguments.get("since_date"),
            arguments.get("limit", 50),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def main():
    s = get_server()
    await s.start()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        await s.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_server.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: add MCP server with 6 tools"
```

---

## Chunk 7: Claude Code Integration

### Task 7: Register MCP with Claude Code

- [ ] **Step 1: Run full test suite to confirm everything passes**

```bash
cd /Users/primathon/Downloads/naukri-mcp
source .venv/bin/activate
pytest tests/ -v --tb=short
```

Expected: All 22+ tests PASS.

- [ ] **Step 2: Copy `.env.example` to `.env` and fill in credentials**

```bash
cp .env.example .env
# Edit .env:
# NAUKRI_EMAIL=your@email.com
# NAUKRI_PASSWORD=yourpassword
# CLAUDE_API_KEY=sk-ant-...
# BASE_RESUME_PATH=./resume_base.pdf
```

- [ ] **Step 3: Place your master resume**

Copy your resume PDF to the path set in `BASE_RESUME_PATH`:

```bash
cp ~/your_resume.pdf /Users/primathon/Downloads/naukri-mcp/resume_base.pdf
```

- [ ] **Step 4: Register MCP with Claude Code**

Claude Code CLI uses this syntax to add an MCP server:

```bash
claude mcp add naukri-mcp \
  "/Users/primathon/Downloads/naukri-mcp/.venv/bin/python server.py"
```

If that does not work, add manually to `~/.claude/settings.json`
(this is for Claude Code CLI, **not** Claude Desktop):

```json
{
  "mcpServers": {
    "naukri-mcp": {
      "command": "/Users/primathon/Downloads/naukri-mcp/.venv/bin/python",
      "args": ["server.py"],
      "cwd": "/Users/primathon/Downloads/naukri-mcp",
      "env": {}
    }
  }
}
```

> **Note:** Claude Desktop uses `~/Library/Application Support/Claude/claude_desktop_config.json` — a different file. Use `~/.claude/settings.json` for Claude Code CLI.

- [ ] **Step 5: Verify MCP is registered**

```bash
claude mcp list
```

Expected: `naukri-mcp` appears in the list.

- [ ] **Step 6: Test end-to-end with dry run**

Start a new Claude Code session and type:

```
Search for Python developer jobs in Bangalore with 3-5 years experience
```

Then approve a job and test apply in dry run mode:

```
Approve the first job and apply to it with dry_run=true
```

Expected: Claude calls the MCP tools, returns job listings, and confirms the application pipeline works without actually submitting.

- [ ] **Step 7: Final commit (use explicit file paths, not `git add .`)**

```bash
git add server.py models.py naukri.py tracker.py resume_tailor.py \
        requirements.txt pytest.ini .gitignore .env.example \
        tests/ docs/
git commit -m "feat: complete naukri-mcp v1 — search, approve, apply with AI resume tailoring"
```

---

## Run All Tests

```bash
cd /Users/primathon/Downloads/naukri-mcp
source .venv/bin/activate
pytest tests/ -v --tb=short
```

Expected output:
```
tests/test_models.py::test_job_model_defaults PASSED
tests/test_models.py::test_job_status_values PASSED
tests/test_models.py::test_job_detail_inherits_job PASSED
tests/test_models.py::test_application_result_success PASSED
tests/test_models.py::test_application_result_failure PASSED
tests/test_models.py::test_naukri_profile_model PASSED
tests/test_models.py::test_job_extra_fields_settable PASSED
tests/test_tracker.py::test_save_and_get_job PASSED
tests/test_tracker.py::test_update_job_status PASSED
tests/test_tracker.py::test_list_jobs_by_status PASSED
tests/test_tracker.py::test_mark_applied PASSED
tests/test_tracker.py::test_mark_failed PASSED
tests/test_tracker.py::test_duplicate_job_skipped PASSED
tests/test_naukri_login.py::test_delay_is_applied PASSED
tests/test_naukri_login.py::test_session_dir_created_with_correct_permissions PASSED
tests/test_naukri_login.py::test_resume_dir_created_with_correct_permissions PASSED
tests/test_resume_tailor.py::test_tailor_returns_string PASSED
tests/test_resume_tailor.py::test_generate_pdf_creates_file PASSED
tests/test_resume_tailor.py::test_extract_text_from_pdf PASSED
tests/test_server.py::test_search_jobs_saves_to_tracker PASSED
tests/test_server.py::test_approve_job_updates_status PASSED
tests/test_server.py::test_apply_job_rejects_non_approved PASSED
tests/test_server.py::test_apply_job_checks_duplicate PASSED
tests/test_server.py::test_list_pending_jobs_returns_found PASSED
tests/test_server.py::test_apply_job_captcha_marks_failed PASSED

25 passed
```

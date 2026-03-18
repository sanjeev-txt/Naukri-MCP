# Naukri MCP v2 — Improvements & Intelligence Features

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auto-questionnaire answering, application status tracking, skills-gap analysis, resume improvement suggestions, job match scoring, bulk apply, company-site detection, and a persistent Playwright browser to make the MCP fully autonomous and self-improving.

**Architecture:** Extend the existing server/naukri/tracker/models stack with new columns, new API calls, and three new intelligence tools (`sync_application_statuses`, `analyze_rejections`, `suggest_improvements`). The candidate profile (CTC, notice period, skills) is loaded from `.env` so questionnaires can be auto-answered without Claude round-trips.

**Tech Stack:** Python 3.11, asyncio, httpx, Playwright (persistent context), aiosqlite, pdfplumber, reportlab, mcp SDK, python-dotenv, pydantic

---

## Scope

This plan is split into 5 independent subsystems, each buildable and testable on its own:

| # | Subsystem | Files |
|---|---|---|
| A | Candidate profile + auto-questionnaire | `models.py`, `tracker.py`, `naukri.py`, `server.py` |
| B | Application status sync | `naukri.py`, `tracker.py`, `models.py`, `server.py` |
| C | Skills-gap analysis + resume suggestions | `analyzer.py` (new), `server.py` |
| D | Job match scoring + smart search | `naukri.py`, `models.py`, `server.py` |
| E | Bulk apply + company-site detection | `naukri.py`, `server.py` |

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `models.py` | Modify | Add `recruiter_status`, `skills_gap`, `match_score`, `CandidateProfile` model |
| `tracker.py` | Modify | Add new DB columns, `update_recruiter_status()`, `get_applied_jobs_for_sync()`, `save_skills_gap()` |
| `naukri.py` | Modify | Add `fetch_application_statuses()`, persistent browser context, company-site status 202 detection |
| `analyzer.py` | Create | `RejectionAnalyzer` — skills-gap computation, pattern aggregation, improvement suggestions |
| `server.py` | Modify | Add tools: `sync_application_statuses`, `analyze_rejections`, `suggest_improvements`, `bulk_apply`; load `CandidateProfile` from env |
| `.env.example` | Modify | Add candidate profile fields |
| `tests/test_analyzer.py` | Create | Unit tests for gap analysis and scoring |
| `tests/test_tracker_v2.py` | Create | Tests for new DB columns and methods (pytest-asyncio style, matching existing tests) |
| `tests/test_naukri_status.py` | Create | Tests for status parsing |
| `requirements.txt` | No change | No new pip dependencies added in this plan (`analyzer.py` uses only stdlib + existing imports) |

---

## Subsystem A — Candidate Profile + Auto-Questionnaire

**Goal:** Load CTC, notice period, experience, location from `.env`. When `apply_to_job` returns `needs_questionnaire`, auto-answer common questions from the profile without calling Claude back. Only surface truly ambiguous questions.

### Task A1: Add `CandidateProfile` model

**Files:**
- Modify: `models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_models.py
def test_candidate_profile_defaults():
    from models import CandidateProfile
    p = CandidateProfile(
        current_ctc=8, expected_ctc=14, notice_period_days=60,
        total_experience_years=4, current_location="Faridabad",
        willing_to_relocate=True,
    )
    assert p.current_ctc == 8.0
    assert p.skills == []

def test_candidate_profile_with_skills():
    from models import CandidateProfile
    p = CandidateProfile(
        current_ctc=8, expected_ctc=14, notice_period_days=60,
        total_experience_years=4, current_location="Faridabad",
        willing_to_relocate=True, skills=["Python", "FastAPI"],
    )
    assert "Python" in p.skills
```

- [ ] **Step 2: Run to confirm failure**
```bash
cd /Users/primathon/Downloads/naukri-mcp
source .venv/bin/activate
pytest tests/test_models.py -v
```
Expected: ImportError / AttributeError — `CandidateProfile` doesn't exist yet

- [ ] **Step 3: Add model to models.py**

```python
class CandidateProfile(BaseModel):
    current_ctc: float          # e.g. 8.0 (LPA)
    expected_ctc: float         # e.g. 14.0
    notice_period_days: int     # e.g. 60
    total_experience_years: float  # e.g. 4.0
    current_location: str       # e.g. "Faridabad"
    willing_to_relocate: bool   # True
    skills: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests — pass**
```bash
pytest tests/test_models.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**
```bash
git add models.py tests/test_models.py
git commit -m "feat(models): add CandidateProfile model"
```

---

### Task A2: Load profile from `.env`

**Files:**
- Modify: `.env.example`
- Modify: `server.py`

- [ ] **Step 1: Add env vars to .env.example**

```bash
# Candidate Profile — used for auto-answering recruiter questions
CANDIDATE_CURRENT_CTC=8
CANDIDATE_EXPECTED_CTC=14
CANDIDATE_NOTICE_DAYS=60
CANDIDATE_EXPERIENCE_YEARS=4
CANDIDATE_LOCATION=Faridabad
CANDIDATE_WILLING_TO_RELOCATE=true
CANDIDATE_SKILLS=Python,Django,FastAPI,LangChain,LangGraph,RAG,LLMs,PostgreSQL,MongoDB,Redis,AWS,Docker,Kafka
```

- [ ] **Step 2: Load profile in NaukriMCPServer.__init__**

In `server.py`, in `NaukriMCPServer.__init__`:
```python
from models import CandidateProfile

self.candidate_profile = CandidateProfile(
    current_ctc=float(os.getenv("CANDIDATE_CURRENT_CTC", "0")),
    expected_ctc=float(os.getenv("CANDIDATE_EXPECTED_CTC", "0")),
    notice_period_days=int(os.getenv("CANDIDATE_NOTICE_DAYS", "60")),
    total_experience_years=float(os.getenv("CANDIDATE_EXPERIENCE_YEARS", "0")),
    current_location=os.getenv("CANDIDATE_LOCATION", ""),
    willing_to_relocate=os.getenv("CANDIDATE_WILLING_TO_RELOCATE", "true").lower() == "true",
    skills=[s.strip() for s in os.getenv("CANDIDATE_SKILLS", "").split(",") if s.strip()],
)
```

- [ ] **Step 3: Verify server starts without error**
```bash
python -c "from server import NaukriMCPServer; s = NaukriMCPServer(); print(s.candidate_profile)"
```
Expected: prints CandidateProfile with values from .env (or defaults)

- [ ] **Step 4: Commit**
```bash
git add .env.example server.py
git commit -m "feat(server): load CandidateProfile from env"
```

---

### Task A3: Auto-answer questionnaire

**Files:**
- Create: `tests/test_auto_questionnaire.py`
- Modify: `server.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auto_questionnaire.py
import pytest
from server import NaukriMCPServer
from models import CandidateProfile
from unittest.mock import MagicMock

def make_server():
    s = NaukriMCPServer.__new__(NaukriMCPServer)
    s.candidate_profile = CandidateProfile(
        current_ctc=8, expected_ctc=14, notice_period_days=60,
        total_experience_years=4, current_location="Faridabad",
        willing_to_relocate=True, skills=["Python", "FastAPI", "LangChain"]
    )
    return s

def test_auto_answer_ctc():
    s = make_server()
    q = {"questionId": "q1", "type": "Text Box", "question": "What is your current CTC in Lacs?"}
    ans = s._auto_answer_question(q)
    assert ans == "8"

def test_auto_answer_experience():
    s = make_server()
    q = {"questionId": "q2", "type": "Text Box", "question": "How many years of Python experience do you have?"}
    ans = s._auto_answer_question(q)
    assert ans == "4"

def test_auto_answer_notice():
    s = make_server()
    q = {"questionId": "q3", "type": "Text Box", "question": "What is your notice period in days?"}
    ans = s._auto_answer_question(q)
    assert ans == "60"

def test_auto_answer_relocate_yes():
    s = make_server()
    q = {"questionId": "q4", "type": "Radio Button", "question": "Are you willing to relocate to Gurugram?",
         "options": [{"optionId": "1", "option": "Yes"}, {"optionId": "2", "option": "No"}]}
    ans = s._auto_answer_question(q)
    assert ans == "1"  # Yes option key

def test_auto_answer_unknown_returns_none():
    s = make_server()
    q = {"questionId": "q5", "type": "Text Box", "question": "Describe your thesis on distributed systems"}
    ans = s._auto_answer_question(q)
    assert ans is None  # cannot auto-answer
```

- [ ] **Step 2: Run tests to confirm they fail**
```bash
cd /Users/primathon/Downloads/naukri-mcp
source .venv/bin/activate
pytest tests/test_auto_questionnaire.py -v
```
Expected: 5 FAILED (AttributeError: _auto_answer_question)

- [ ] **Step 3: Implement `_auto_answer_question` in server.py**

Add method to `NaukriMCPServer`:
```python
def _auto_answer_question(self, question: dict) -> str | None:
    """
    Auto-answer a recruiter screening question from candidate profile.
    Returns answer string, or None if ambiguous/unknown.
    """
    p = self.candidate_profile
    q_text = (question.get("question") or "").lower()
    q_type = question.get("type", "")
    options = question.get("options") or []

    # Helper: find radio option key by label match
    def radio_key(label: str) -> str | None:
        label_lower = label.lower()
        for opt in options:
            if label_lower in (opt.get("option") or "").lower():
                return str(opt.get("optionId") or opt.get("id") or "")
        return None

    # CTC questions
    if any(k in q_text for k in ["current ctc", "current salary", "ctc in lacs", "ctc per annum"]):
        if q_type in ("Text Box", "text"):
            return str(int(p.current_ctc)) if p.current_ctc == int(p.current_ctc) else str(p.current_ctc)

    if any(k in q_text for k in ["expected ctc", "expected salary", "salary expectation"]):
        if q_type in ("Text Box", "text"):
            return str(int(p.expected_ctc)) if p.expected_ctc == int(p.expected_ctc) else str(p.expected_ctc)

    # Notice period
    if any(k in q_text for k in ["notice period", "notice in days", "joining time"]):
        if q_type in ("Text Box", "text"):
            return str(p.notice_period_days)
        # Radio: look for matching option
        for opt in options:
            opt_text = (opt.get("option") or "").lower()
            if str(p.notice_period_days) in opt_text or "2 month" in opt_text and p.notice_period_days <= 60:
                return str(opt.get("optionId") or "")

    # Experience questions
    if any(k in q_text for k in ["years of experience", "experience do you have", "total experience", "how many years"]):
        if q_type in ("Text Box", "text"):
            exp = p.total_experience_years
            return str(int(exp)) if exp == int(exp) else str(exp)
        # Radio: find matching range
        for opt in options:
            opt_text = (opt.get("option") or "").lower()
            if str(int(p.total_experience_years)) in opt_text:
                return str(opt.get("optionId") or "")

    # Location / relocation
    if any(k in q_text for k in ["relocat", "willing to move", "currently residing", "work from office", "onsite"]):
        if q_type == "Radio Button":
            if p.willing_to_relocate:
                return radio_key("yes") or radio_key("comfortable") or None
            else:
                return radio_key("no") or None
        if q_type in ("Text Box", "text"):
            return p.current_location

    # Current location / city
    if any(k in q_text for k in ["current location", "current city", "where are you based"]):
        if q_type in ("Text Box", "text"):
            return p.current_location

    return None  # Cannot auto-answer
```

- [ ] **Step 4: Run tests — all should pass**
```bash
pytest tests/test_auto_questionnaire.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Wire auto-answer into `_apply_job`**

In `server.py`, `_apply_job` method, when `result.get("needs_questionnaire")` is True:
```python
if isinstance(result, dict) and result.get("needs_questionnaire"):
    questions = result.get("questions", [])
    auto_answers = {}
    unanswered = []

    for q in questions:
        q_id = str(q.get("questionId") or q.get("id") or "")
        ans = self._auto_answer_question(q)
        if ans is not None:
            auto_answers[q_id] = ans
        else:
            unanswered.append(q)

    if not unanswered:
        # Fully auto-answered — submit immediately
        return await self._submit_questionnaire(job_id, auto_answers)
    else:
        # Return partial answers + questions Claude/user must answer
        result["auto_answered"] = auto_answers
        result["unanswered_questions"] = unanswered
        result["message"] = (
            f"Auto-answered {len(auto_answers)} question(s). "
            f"{len(unanswered)} question(s) need your input. "
            "Call submit_questionnaire with job_id and merged answers dict."
        )
        return result
```

- [ ] **Step 6: Commit**
```bash
git add server.py tests/test_auto_questionnaire.py
git commit -m "feat(server): auto-answer recruiter questionnaires from candidate profile"
```

---

## Subsystem B — Application Status Sync

**Goal:** Poll Naukri's apply history API to update `recruiter_status` for all applied jobs. New tool: `sync_application_statuses`.

### Task B1: Extend DB schema for status tracking

**Files:**
- Create: `tests/test_tracker_v2.py`
- Modify: `tracker.py`

- [ ] **Step 1: Write failing tests**

> Use pytest-asyncio style matching the existing `tests/` conventions (async fixtures + async test functions).

```python
# tests/test_tracker_v2.py
import pytest
import pytest_asyncio
from tracker import JobTracker
from models import Job
from datetime import datetime

def make_job(job_id="j1"):
    return Job(id=job_id, title="Dev", company="ACME", location="Delhi",
               url=f"https://naukri.com/{job_id}", found_at=datetime.now(), status="applied")

@pytest_asyncio.fixture
async def tracker(tmp_path):
    t = JobTracker(db_path=str(tmp_path / "test.db"))
    await t.init()
    yield t
    await t.close()

@pytest.mark.asyncio
async def test_update_recruiter_status(tracker):
    await tracker.save_job(make_job("j1"))
    await tracker.update_recruiter_status("j1", "viewed")
    job = await tracker.get_job("j1")
    assert job.recruiter_status == "viewed"

@pytest.mark.asyncio
async def test_get_applied_jobs_for_sync(tracker):
    await tracker.save_job(make_job("j1"))
    await tracker.update_status("j1", "applied")
    j2 = make_job("j2")
    j2.status = "found"
    await tracker.save_job(j2)
    jobs = await tracker.get_applied_jobs_for_sync()
    assert len(jobs) == 1
    assert jobs[0].id == "j1"

@pytest.mark.asyncio
async def test_save_skills_gap(tracker):
    await tracker.save_job(make_job("j1"))
    await tracker.save_skills_gap("j1", ["Kubernetes", "Go"], 45)
    job = await tracker.get_job("j1")
    assert job.skills_gap == ["Kubernetes", "Go"]
    assert job.match_score == 45
```

- [ ] **Step 2: Run to confirm failures**
```bash
pytest tests/test_tracker_v2.py -v
```
Expected: 3 FAILED

- [ ] **Step 3: Extend tracker.py**

Add new columns in `init()`:
```python
await self._conn.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS recruiter_status TEXT")
await self._conn.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS status_checked_at DATETIME")
await self._conn.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS skills_gap TEXT")
await self._conn.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS match_score INTEGER")
```

> Note: SQLite doesn't support `IF NOT EXISTS` on ALTER. Use a try/except instead:
```python
for col_sql in [
    "ALTER TABLE jobs ADD COLUMN recruiter_status TEXT",
    "ALTER TABLE jobs ADD COLUMN status_checked_at DATETIME",
    "ALTER TABLE jobs ADD COLUMN skills_gap TEXT",
    "ALTER TABLE jobs ADD COLUMN match_score INTEGER",
]:
    try:
        await self._conn.execute(col_sql)
    except Exception:
        pass  # column already exists
await self._conn.commit()
```

Add new methods:
```python
async def update_recruiter_status(self, job_id: str, recruiter_status: str):
    # datetime already imported at module level in tracker.py
    await self._conn.execute(
        "UPDATE jobs SET recruiter_status = ?, status_checked_at = ? WHERE id = ?",
        (recruiter_status, datetime.now().isoformat(), job_id)
    )
    await self._conn.commit()

async def get_applied_jobs_for_sync(self) -> list[Job]:
    """Return all jobs with status='applied' for status polling."""
    async with self._conn.execute(
        "SELECT * FROM jobs WHERE status = 'applied' ORDER BY applied_at DESC"
    ) as cursor:
        rows = await cursor.fetchall()
    return [self._row_to_job(r) for r in rows]

async def save_skills_gap(self, job_id: str, gap_skills: list[str], match_score: int):
    import json
    await self._conn.execute(
        "UPDATE jobs SET skills_gap = ?, match_score = ? WHERE id = ?",
        (json.dumps(gap_skills), match_score, job_id)
    )
    await self._conn.commit()
```

Update `_row_to_job` to include new fields. Replace the full method:
```python
def _row_to_job(self, row) -> Job:
    import json as _json
    data = dict(row)
    data["skills_required"] = _json.loads(data["skills_required"] or "[]")
    data["found_at"] = datetime.fromisoformat(data["found_at"])
    if data.get("applied_at"):
        data["applied_at"] = datetime.fromisoformat(data["applied_at"])
    if data.get("status_checked_at"):
        data["status_checked_at"] = datetime.fromisoformat(data["status_checked_at"])
    raw_gap = data.get("skills_gap")
    data["skills_gap"] = _json.loads(raw_gap) if raw_gap else []
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
        # New v2 fields
        recruiter_status=data.get("recruiter_status"),
        status_checked_at=data.get("status_checked_at"),
        skills_gap=data["skills_gap"],
        match_score=data.get("match_score"),
    )
```

Update `Job` model in `models.py` to add optional fields:
```python
recruiter_status: str | None = None   # 'viewed'|'shortlisted'|'rejected'|'expired'
status_checked_at: datetime | None = None
skills_gap: list[str] = Field(default_factory=list)
match_score: int | None = None
```

- [ ] **Step 4: Run tests — all pass**
```bash
pytest tests/test_tracker_v2.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**
```bash
git add tracker.py models.py tests/test_tracker_v2.py
git commit -m "feat(tracker): add recruiter_status, skills_gap, match_score columns"
```

---

### Task B2: Fetch application statuses from Naukri API

**Files:**
- Create: `tests/test_naukri_status.py`
- Modify: `naukri.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_naukri_status.py
from naukri import NaukriClient

def test_parse_recruiter_status_shortlisted():
    client = NaukriClient.__new__(NaukriClient)
    entry = {"applyStatus": "Shortlisted", "jobId": "123"}
    status = client._parse_recruiter_status(entry)
    assert status == "shortlisted"

def test_parse_recruiter_status_viewed():
    client = NaukriClient.__new__(NaukriClient)
    entry = {"applyStatus": "Viewed", "jobId": "123"}
    assert client._parse_recruiter_status(entry) == "viewed"

def test_parse_recruiter_status_rejected():
    client = NaukriClient.__new__(NaukriClient)
    entry = {"applyStatus": "Rejected", "jobId": "123"}
    assert client._parse_recruiter_status(entry) == "rejected"

def test_parse_recruiter_status_applied():
    client = NaukriClient.__new__(NaukriClient)
    entry = {"applyStatus": "Applied", "jobId": "123"}
    assert client._parse_recruiter_status(entry) == "applied"
```

- [ ] **Step 2: Run to confirm failures**
```bash
pytest tests/test_naukri_status.py -v
```
Expected: 4 FAILED

- [ ] **Step 3: Add methods to naukri.py**

```python
def _parse_recruiter_status(self, entry: dict) -> str:
    """Normalize Naukri applyStatus string to our internal status."""
    raw = (entry.get("applyStatus") or entry.get("status") or "").lower()
    if "shortlist" in raw:
        return "shortlisted"
    if "reject" in raw or "not select" in raw:
        return "rejected"
    if "view" in raw or "seen" in raw:
        return "viewed"
    if "expir" in raw or "closed" in raw:
        return "expired"
    return "applied"

async def fetch_application_statuses(self, job_ids: list[str]) -> dict[str, str]:
    """
    Fetch current recruiter status for a list of applied job IDs.
    Returns {job_id: recruiter_status}.
    Uses APPLY_HISTORY_URL.
    """
    await self.login()
    try:
        data = await self._get(
            APPLY_HISTORY_URL,
            params={"appPage": 1, "pageSize": 200},
        )
    except Exception as e:
        raise NaukriError(f"Could not fetch apply history: {e}")

    applications = (
        data.get("jobApplyList")
        or data.get("applications")
        or data.get("data")
        or []
    )

    id_set = set(str(j) for j in job_ids)
    result = {}
    for app in applications:
        jid = str(app.get("jobId") or app.get("id") or "")
        if jid in id_set:
            result[jid] = self._parse_recruiter_status(app)
    return result
```

- [ ] **Step 4: Run tests — all pass**
```bash
pytest tests/test_naukri_status.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**
```bash
git add naukri.py tests/test_naukri_status.py
git commit -m "feat(naukri): add fetch_application_statuses and status parser"
```

---

### Task B3: Add `sync_application_statuses` MCP tool

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add handler method in NaukriMCPServer**

```python
async def _sync_application_statuses(self) -> dict:
    """Poll Naukri for recruiter status on all applied jobs and update tracker."""
    applied_jobs = await self.tracker.get_applied_jobs_for_sync()
    if not applied_jobs:
        return {"message": "No applied jobs to sync.", "updated": []}

    job_ids = [j.id for j in applied_jobs]
    statuses = await self.browser.fetch_application_statuses(job_ids)

    updated = []
    for job in applied_jobs:
        new_status = statuses.get(job.id)
        if new_status and new_status != job.recruiter_status:
            await self.tracker.update_recruiter_status(job.id, new_status)
            updated.append({
                "job_id": job.id,
                "company": job.company,
                "title": job.title,
                "old_status": job.recruiter_status or "unknown",
                "new_status": new_status,
            })

    return {
        "total_checked": len(applied_jobs),
        "updated": updated,
        "message": f"Synced {len(applied_jobs)} applications. {len(updated)} status change(s) found.",
    }
```

- [ ] **Step 2: Register the tool in `list_tools()`**

```python
types.Tool(
    name="sync_application_statuses",
    description=(
        "Poll Naukri for recruiter status on all your applied jobs "
        "(Viewed / Shortlisted / Rejected / Expired). "
        "Run this 3-7 days after applying to see recruiter activity."
    ),
    inputSchema={"type": "object", "properties": {}},
),
```

- [ ] **Step 3: Add to `call_tool()` dispatcher**

```python
elif name == "sync_application_statuses":
    result = await s._sync_application_statuses()
```

- [ ] **Step 4: Manual smoke test**
```bash
python -c "
import asyncio
from server import NaukriMCPServer
async def test():
    s = NaukriMCPServer()
    await s.start()
    print(await s._sync_application_statuses())
asyncio.run(test())
"
```
Expected: JSON with `total_checked`, `updated`, `message`

- [ ] **Step 5: Commit**
```bash
git add server.py
git commit -m "feat(server): add sync_application_statuses tool"
```

---

## Subsystem C — Skills-Gap Analysis + Resume Intelligence

**Goal:** After syncing statuses, analyze which skills are consistently missing from rejected/unviewed applications. Generate ranked improvement suggestions for resume and Naukri profile.

### Task C1: Create `analyzer.py`

**Files:**
- Create: `analyzer.py`
- Create: `tests/test_analyzer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analyzer.py
import pytest
from analyzer import RejectionAnalyzer
from models import Job, CandidateProfile
from datetime import datetime

def make_job(job_id, skills_required, recruiter_status, match_score=None, skills_gap=None):
    return Job(
        id=job_id, title="Dev", company="ACME", location="Delhi",
        url=f"https://naukri.com/{job_id}", found_at=datetime.now(),
        status="applied", skills_required=skills_required,
        recruiter_status=recruiter_status,
        skills_gap=skills_gap or [],
        match_score=match_score,
    )

@pytest.fixture
def profile():
    return CandidateProfile(
        current_ctc=8, expected_ctc=14, notice_period_days=60,
        total_experience_years=4, current_location="Faridabad",
        willing_to_relocate=True,
        skills=["Python", "Django", "FastAPI", "LangChain", "PostgreSQL"],
    )

def test_compute_match_score(profile):
    a = RejectionAnalyzer(profile)
    score = a.compute_match_score(["Python", "FastAPI", "Kubernetes"], profile.skills)
    assert score == pytest.approx(66, abs=5)  # 2/3 matched

def test_compute_gap(profile):
    a = RejectionAnalyzer(profile)
    gap = a.compute_gap(["Python", "FastAPI", "Kubernetes", "Go"], profile.skills)
    assert "Kubernetes" in gap
    assert "Go" in gap
    assert "Python" not in gap

def test_aggregate_missing_skills(profile):
    a = RejectionAnalyzer(profile)
    jobs = [
        make_job("j1", ["Python", "Kubernetes", "Go"], "rejected", skills_gap=["Kubernetes", "Go"]),
        make_job("j2", ["Python", "Kubernetes", "Kafka"], "viewed", skills_gap=["Kubernetes", "Kafka"]),
        make_job("j3", ["Python", "Kubernetes", "Redis"], "applied", skills_gap=["Kubernetes", "Redis"]),
    ]
    freq = a.aggregate_missing_skills(jobs)
    assert freq["Kubernetes"] == 3
    assert freq["Go"] == 1

def test_suggest_resume_improvements(profile):
    a = RejectionAnalyzer(profile)
    freq = {"Kubernetes": 5, "Go": 3, "System Design": 2}
    suggestions = a.suggest_resume_improvements(freq, min_count=2)
    assert any("Kubernetes" in s for s in suggestions)
    assert any("Go" in s for s in suggestions)

def test_classify_rejection_reason(profile):
    a = RejectionAnalyzer(profile)
    # never viewed = ATS issue
    assert a.classify_rejection_reason(None) == "ats_filtered"
    # viewed but not shortlisted = content issue
    assert a.classify_rejection_reason("viewed") == "content_gap"
    assert a.classify_rejection_reason("shortlisted") == "shortlisted"
```

- [ ] **Step 2: Run to confirm failures**
```bash
pytest tests/test_analyzer.py -v
```
Expected: 5 FAILED (ModuleNotFoundError: analyzer)

- [ ] **Step 3: Create `analyzer.py`**

```python
# analyzer.py
from collections import Counter
from models import Job, CandidateProfile


class RejectionAnalyzer:
    def __init__(self, profile: CandidateProfile):
        self.profile = profile
        self._profile_skills_lower = {s.lower() for s in profile.skills}

    def compute_match_score(self, jd_skills: list[str], profile_skills: list[str]) -> int:
        """Return 0-100 score: % of JD skills present in profile."""
        if not jd_skills:
            return 100
        profile_lower = {s.lower() for s in profile_skills}
        matched = sum(1 for s in jd_skills if s.lower() in profile_lower)
        return int(matched / len(jd_skills) * 100)

    def compute_gap(self, jd_skills: list[str], profile_skills: list[str]) -> list[str]:
        """Return skills in JD that are NOT in the profile."""
        profile_lower = {s.lower() for s in profile_skills}
        return [s for s in jd_skills if s.lower() not in profile_lower]

    def classify_rejection_reason(self, recruiter_status: str | None) -> str:
        """
        Classify why a job wasn't shortlisted.
        - None / 'applied' = ATS never surfaced the resume (keyword mismatch)
        - 'viewed' = recruiter saw it but didn't shortlist (content gap)
        - 'shortlisted' = success
        - 'rejected' = explicit rejection
        """
        if recruiter_status in (None, "applied"):
            return "ats_filtered"
        if recruiter_status == "viewed":
            return "content_gap"
        if recruiter_status == "shortlisted":
            return "shortlisted"
        if recruiter_status == "rejected":
            return "content_gap"
        return "unknown"

    def aggregate_missing_skills(self, jobs: list[Job]) -> dict[str, int]:
        """
        Count how often each missing skill appears across rejected/unshortlisted jobs.
        Returns {skill: frequency} sorted descending.
        """
        counter: Counter = Counter()
        for job in jobs:
            for skill in (job.skills_gap or []):
                counter[skill] += 1
        return dict(counter.most_common())

    def suggest_resume_improvements(
        self, freq: dict[str, int], min_count: int = 2
    ) -> list[str]:
        """Generate human-readable resume improvement suggestions."""
        suggestions = []
        for skill, count in freq.items():
            if count >= min_count:
                suggestions.append(
                    f"Add '{skill}' to your resume — missing from {count} job(s) you applied to."
                )
        return suggestions

    def suggest_profile_improvements(self, freq: dict[str, int], min_count: int = 2) -> list[str]:
        """Suggest Naukri profile keyword additions."""
        suggestions = []
        for skill, count in freq.items():
            if count >= min_count and skill.lower() not in self._profile_skills_lower:
                suggestions.append(
                    f"Add '{skill}' to your Naukri profile skills — demanded in {count} target role(s)."
                )
        return suggestions

    def analyze(self, applied_jobs: list[Job]) -> dict:
        """
        Full analysis: categorize jobs, find gaps, return structured insights.
        """
        shortlisted = [j for j in applied_jobs if j.recruiter_status == "shortlisted"]
        viewed_not_shortlisted = [j for j in applied_jobs if j.recruiter_status == "viewed"]
        never_viewed = [j for j in applied_jobs if j.recruiter_status in (None, "applied")]
        rejected = [j for j in applied_jobs if j.recruiter_status == "rejected"]

        # All non-successful jobs for gap analysis
        unsuccessful = viewed_not_shortlisted + never_viewed + rejected
        freq = self.aggregate_missing_skills(unsuccessful)

        avg_score = (
            sum(j.match_score for j in applied_jobs if j.match_score is not None) /
            max(len([j for j in applied_jobs if j.match_score is not None]), 1)
        )

        return {
            "total_applied": len(applied_jobs),
            "shortlisted": len(shortlisted),
            "viewed_not_shortlisted": len(viewed_not_shortlisted),
            "never_viewed": len(never_viewed),
            "rejected": len(rejected),
            "average_match_score": round(avg_score, 1),
            "common_missing_skills": freq,
            "ats_issue": len(never_viewed) > len(applied_jobs) * 0.5,
            "content_issue": len(viewed_not_shortlisted) > len(shortlisted),
            "resume_suggestions": self.suggest_resume_improvements(freq),
            "profile_suggestions": self.suggest_profile_improvements(freq),
        }
```

- [ ] **Step 4: Run tests — all pass**
```bash
pytest tests/test_analyzer.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**
```bash
git add analyzer.py tests/test_analyzer.py
git commit -m "feat(analyzer): add RejectionAnalyzer with gap analysis and suggestions"
```

---

### Task C2: Compute and store gap when applying

**Files:**
- Modify: `server.py`

**Goal:** When `apply_job` is called on an approved job, compute `match_score` and `skills_gap` from the job's `skills_required` vs candidate profile and store in DB.

- [ ] **Step 1: Import and wire in server.py**

In `NaukriMCPServer.__init__`, after loading profile:
```python
from analyzer import RejectionAnalyzer
self.analyzer = RejectionAnalyzer(self.candidate_profile)
```

In `_apply_job`, insert skills-gap computation **after** the `is_duplicate` check and **before** calling `self.browser.apply_to_job`. Exact insertion point — place immediately before the `try: result = await self.browser.apply_to_job(...)` line:
```python
# Compute and store skills gap AFTER guards, BEFORE applying
if job.skills_required:
    gap = self.analyzer.compute_gap(job.skills_required, self.candidate_profile.skills)
    score = self.analyzer.compute_match_score(job.skills_required, self.candidate_profile.skills)
    await self.tracker.save_skills_gap(job.id, gap, score)

try:
    result = await self.browser.apply_to_job(job.url, dry_run=dry_run)
    ...
```

- [ ] **Step 2: Verify no regressions**
```bash
pytest tests/ -v
```
Expected: All previously passing tests still pass

- [ ] **Step 3: Commit**
```bash
git add server.py
git commit -m "feat(server): compute and store skills_gap at apply time"
```

---

### Task C3: Add `analyze_rejections` and `suggest_improvements` MCP tools

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add handler methods**

```python
async def _analyze_rejections(self, since_days: int = 30) -> dict:
    """Analyze all applied jobs to surface rejection patterns."""
    from datetime import timedelta
    since_date = (datetime.now() - timedelta(days=since_days)).isoformat()
    applied_jobs = await self.tracker.list_jobs(status="applied", since_date=since_date)
    if not applied_jobs:
        return {"message": f"No applied jobs found in the last {since_days} days."}
    return self.analyzer.analyze(applied_jobs)

async def _suggest_improvements(self) -> dict:
    """Aggregate all time rejection data and return resume + profile improvements."""
    applied_jobs = await self.tracker.list_jobs(status="applied")
    if not applied_jobs:
        return {"message": "No applied jobs in tracker yet. Apply to some jobs first."}

    analysis = self.analyzer.analyze(applied_jobs)

    strategy = []
    if analysis["ats_issue"]:
        strategy.append(
            f"{analysis['never_viewed']} of your applications were never viewed. "
            "This is an ATS keyword issue — add missing skills to your resume headline and skills section."
        )
    if analysis["content_issue"]:
        strategy.append(
            f"{analysis['viewed_not_shortlisted']} applications were viewed but not shortlisted. "
            "Recruiters are reading your resume but not finding enough match — strengthen project descriptions."
        )
    if analysis["shortlisted"] > 0:
        strategy.append(
            f"You were shortlisted {analysis['shortlisted']} time(s) — "
            "identify what those job descriptions had in common with your profile."
        )

    return {
        "summary": {
            "total_applied": analysis["total_applied"],
            "shortlisted": analysis["shortlisted"],
            "shortlist_rate": f"{round(analysis['shortlisted'] / max(analysis['total_applied'], 1) * 100, 1)}%",
            "average_match_score": analysis["average_match_score"],
        },
        "diagnosis": strategy,
        "top_missing_skills": list(analysis["common_missing_skills"].items())[:10],
        "resume_improvements": analysis["resume_suggestions"],
        "profile_improvements": analysis["profile_suggestions"],
    }
```

- [ ] **Step 2: Register both tools in `list_tools()`**

```python
types.Tool(
    name="analyze_rejections",
    description=(
        "Analyze your recent job applications to find rejection patterns. "
        "Shows shortlist rate, which skills are commonly missing, "
        "and whether the issue is ATS filtering or content gaps. "
        "Run sync_application_statuses first for fresh data."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "since_days": {"type": "integer", "default": 30,
                           "description": "Look back this many days (default 30)"},
        },
    },
),
types.Tool(
    name="suggest_improvements",
    description=(
        "Generate specific resume and Naukri profile improvement suggestions "
        "based on skills gaps found across all rejected applications. "
        "Returns ranked list of missing skills and actionable edits."
    ),
    inputSchema={"type": "object", "properties": {}},
),
```

- [ ] **Step 3: Add to `call_tool()` dispatcher**

```python
elif name == "analyze_rejections":
    result = await s._analyze_rejections(arguments.get("since_days", 30))
elif name == "suggest_improvements":
    result = await s._suggest_improvements()
```

- [ ] **Step 4: Run full test suite**
```bash
pytest tests/ -v
```
Expected: All pass

- [ ] **Step 5: Commit**
```bash
git add server.py
git commit -m "feat(server): add analyze_rejections and suggest_improvements tools"
```

---

## Subsystem D — Job Match Scoring + Smart Search

**Goal:** Add `match_score` to every job returned by `search_jobs`. Filter or rank results by score so Claude only shows high-relevance jobs.

### Task D1: Score jobs at search time

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Compute match score in `_search_jobs`**

After fetching jobs:
```python
async def _search_jobs(self, title, location, experience, skills, max_results):
    jobs = await self.browser.search_jobs(title, location, experience, skills, max_results)
    for job in jobs:
        # Compute match score and gap vs candidate profile
        if job.skills_required and self.candidate_profile.skills:
            job.match_score = self.analyzer.compute_match_score(
                job.skills_required, self.candidate_profile.skills
            )
            gap = self.analyzer.compute_gap(job.skills_required, self.candidate_profile.skills)
        else:
            job.match_score = None
            gap = []
        await self.tracker.save_job(job)
        if gap:
            await self.tracker.save_skills_gap(job.id, gap, job.match_score or 0)
    # Sort by match score descending
    jobs.sort(key=lambda j: j.match_score or 0, reverse=True)
    return [j.model_dump(mode="json") for j in jobs]
```

- [ ] **Step 2: Verify tests still pass**
```bash
pytest tests/ -v
```

- [ ] **Step 3: Commit**
```bash
git add server.py
git commit -m "feat(server): compute match_score at search time, sort results by score"
```

---

## Subsystem E — Bulk Apply + Company-Site Detection

**Goal:** Single `bulk_apply` tool applies to all approved jobs in sequence. Detect status 202 ("apply on company site") and return external URL cleanly instead of failing silently.

### Task E1: Detect apply-on-company-site (status 202)

**Files:**
- Modify: `naukri.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_naukri_status.py (extend existing file)
def test_parse_apply_result_company_site():
    client = NaukriClient.__new__(NaukriClient)
    # status 202 means "apply on company site"
    job_entry = {"jobId": "123", "status": 202, "jdURL": "https://company.com/apply"}
    result = client._parse_apply_result("123", {"jobs": [job_entry]})
    assert result["apply_on_company_site"] is True
    assert "https://company.com/apply" in result["external_url"]
```

- [ ] **Step 2: Add `_parse_apply_result` to naukri.py**

```python
def _parse_apply_result(self, job_id: str, data: dict) -> dict:
    """Parse apply API response and return structured result."""
    jobs_list = data.get("jobs", [])
    job_entry = next((j for j in jobs_list if str(j.get("jobId")) == job_id), {})
    status_code = job_entry.get("status")

    if status_code == 202:
        # Apply on company site
        external_url = job_entry.get("jdURL") or job_entry.get("redirectURL") or ""
        return {
            "apply_on_company_site": True,
            "external_url": external_url,
            "job_id": job_id,
            "message": f"This job requires applying on the company site: {external_url}",
        }

    if status_code == 409001 or data.get("applyStatus", {}).get(job_id) == 409001:
        raise NaukriError(f"Already applied to job {job_id}")

    if status_code is not None and status_code != 200:
        msg = job_entry.get("message", "Unknown error")
        raise NaukriError(f"Apply failed: {msg}")

    return {"success": True}
```

Update `apply_to_job` Step 3 (no-questionnaire path) to use this:
```python
result = self._parse_apply_result(job_id, data)
if result.get("apply_on_company_site"):
    return result  # Caller handles company-site redirect
```

- [ ] **Step 3: Run tests**
```bash
pytest tests/test_naukri_status.py -v
```
Expected: All pass

- [ ] **Step 4: Handle in server.py `_apply_job`**

After `result = await self.browser.apply_to_job(...)`:
```python
if isinstance(result, dict) and result.get("apply_on_company_site"):
    await self.tracker.update_status(job_id, "applied_externally")
    return {
        "success": True,
        "apply_on_company_site": True,
        "external_url": result["external_url"],
        "message": result["message"],
    }
```

- [ ] **Step 5: Commit**
```bash
git add naukri.py server.py tests/test_naukri_status.py
git commit -m "feat(naukri): detect apply-on-company-site status 202, return external URL"
```

---

### Task E2: Add `bulk_apply` tool

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add handler**

```python
async def _bulk_apply(self, job_ids: list[str] | None = None) -> dict:
    """
    Apply to all approved jobs (or a specific list).
    Auto-answers questionnaires from candidate profile.
    Returns a summary report.
    """
    if job_ids:
        jobs = [await self.tracker.get_job(jid) for jid in job_ids]
        jobs = [j for j in jobs if j and j.status == "approved"]
    else:
        jobs = await self.tracker.list_jobs(status="approved")

    if not jobs:
        return {"message": "No approved jobs to apply to. Use approve_job first.", "results": []}

    results = []
    for job in jobs:
        try:
            outcome = await self._apply_job(job.id, dry_run=False)
            results.append({
                "job_id": job.id,
                "company": job.company,
                "title": job.title,
                "outcome": "applied" if outcome.get("success") else "failed",
                "detail": outcome,
            })
        except Exception as e:
            results.append({
                "job_id": job.id,
                "company": job.company,
                "title": job.title,
                "outcome": "error",
                "detail": str(e),
            })

    applied = [r for r in results if r["outcome"] == "applied"]
    # Questionnaire-required: _apply_job returns needs_questionnaire=True — not a failure
    questionnaire_needed = [
        r for r in results
        if isinstance(r.get("detail"), dict) and r["detail"].get("needs_questionnaire")
    ]
    # Company-site redirects: _apply_job returns apply_on_company_site=True
    external = [
        r for r in results
        if isinstance(r.get("detail"), dict) and r["detail"].get("apply_on_company_site")
    ]
    failed = [
        r for r in results
        if r["outcome"] in ("failed", "error")
        and r not in questionnaire_needed
        and r not in external
    ]

    return {
        "total": len(results),
        "applied": len(applied),
        "failed": len(failed),
        "apply_on_company_site": len(external),
        "needs_manual_questionnaire": len(questionnaire_needed),
        "results": results,
        "summary": (
            f"{len(applied)}/{len(results)} applications submitted. "
            f"{len(external)} require manual action on company site. "
            f"{len(questionnaire_needed)} have unresolved questionnaire questions. "
            f"{len(failed)} failed."
        ),
    }
```

- [ ] **Step 2: Register tool in `list_tools()`**

```python
types.Tool(
    name="bulk_apply",
    description=(
        "Apply to all approved jobs in one command. "
        "Auto-answers common recruiter questions from your candidate profile. "
        "Pass job_ids to apply to specific jobs, or omit to apply to all approved jobs."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "job_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific job IDs to apply to (optional — omit for all approved)",
            },
        },
    },
),
```

- [ ] **Step 3: Add to `call_tool()` dispatcher**

```python
elif name == "bulk_apply":
    result = await s._bulk_apply(arguments.get("job_ids"))
```

- [ ] **Step 4: Run full test suite**
```bash
pytest tests/ -v
```
Expected: All pass

- [ ] **Step 5: Commit**
```bash
git add server.py
git commit -m "feat(server): add bulk_apply tool for one-command batch applications"
```

---

## Final Integration Test

- [ ] **Step 1: Start MCP server and verify all tools listed**
```bash
python -c "
import asyncio
from mcp.server.stdio import stdio_server
from server import app, get_server
# Just list tools without running full server
s = get_server()
print('Server initialized OK')
print('Candidate profile:', s.candidate_profile)
print('Analyzer:', s.analyzer)
"
```
Expected: prints profile and analyzer without errors

- [ ] **Step 2: Run complete test suite**
```bash
pytest tests/ -v --tb=short
```
Expected: All tests pass

- [ ] **Step 3: Final commit**
```bash
git add -A
git commit -m "feat: naukri-mcp v2 — auto-questionnaire, status tracking, gap analysis, bulk apply"
```

---

## New Tool Summary

| Tool | Purpose |
|---|---|
| `bulk_apply` | Apply to all approved jobs in one command |
| `sync_application_statuses` | Poll Naukri for recruiter activity on applied jobs |
| `analyze_rejections` | Find patterns in why applications aren't getting shortlisted |
| `suggest_improvements` | Get ranked resume + profile improvement actions |

## Config Summary (`.env` additions)

```env
CANDIDATE_CURRENT_CTC=8
CANDIDATE_EXPECTED_CTC=14
CANDIDATE_NOTICE_DAYS=60
CANDIDATE_EXPERIENCE_YEARS=4
CANDIDATE_LOCATION=Faridabad
CANDIDATE_WILLING_TO_RELOCATE=true
CANDIDATE_SKILLS=Python,Django,FastAPI,LangChain,LangGraph,RAG,LLMs,PostgreSQL,MongoDB,Redis,AWS,Docker,Kafka
```

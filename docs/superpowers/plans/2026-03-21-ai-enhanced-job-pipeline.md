# AI-Enhanced Job Application Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add iterative resume-JD scoring and tailoring to the Naukri-MCP, so each job application uses the best-fit resume version.

**Architecture:** New `resume_scorer.py` handles local keyword+TF-IDF scoring. Modified `resume_tailor.py` reads from YAML master resume, generates ATS-optimized PDFs. Modified `server.py` adds 3 new MCP tools (`score_resume_match`, `upload_and_apply`, `get_application_stats`) and modifies 2 existing ones (`get_resume_data`, `generate_resume`). Modified `tracker.py` adds `resume_versions` table. Claude orchestrates the score→tailor→re-score loop.

**Tech Stack:** Python 3.12, scikit-learn (TF-IDF), PyYAML, reportlab (PDF), aiosqlite, Pydantic, MCP SDK

**Spec:** `docs/superpowers/specs/2026-03-21-ai-enhanced-job-pipeline-design.md`

**Project root:** `/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP`

**Test command:** `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/ -v`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `models.py` | Modify | Add `ResumeScore`, `ResumeVersion`, `MasterResume` Pydantic models |
| `resume_scorer.py` | Create | Keyword extraction + TF-IDF scoring engine |
| `resume_tailor.py` | Modify | Remove `extract_text`, add `load_yaml`, ATS-optimized PDF with HTML escaping |
| `tracker.py` | Modify | Add `resume_versions` table, `save_resume_version`, `get_best_resume`, `get_iteration_count`, `get_application_stats` |
| `server.py` | Modify | New tools: `score_resume_match`, `upload_and_apply`, `get_application_stats`. Modified: `get_resume_data`, `generate_resume` (renamed) |
| `~/.naukri-mcp/master_resume.yaml` | Create | Navjeet's structured resume data |
| `requirements.txt` | Modify | Add `scikit-learn`, `pyyaml`. Remove `pdfplumber` |
| `.env` | Modify | Add new config vars (not committed — update `.env.example` instead) |
| `tests/fixtures/sample_resume.yaml` | Create | Minimal test resume |
| `tests/fixtures/sample_jd.txt` | Create | Sample JD for scoring tests |
| `tests/fixtures/sample_jd_poor_match.txt` | Create | Poor-match JD for skip threshold tests |
| `tests/test_models_scoring.py` | Create | Tests for new Pydantic models |
| `tests/test_resume_scorer.py` | Create | Scoring engine tests |
| `tests/test_resume_tailor_v2.py` | Create | ATS PDF generation tests |
| `tests/test_tracker_versions.py` | Create | Resume version tracking tests |
| `tests/test_server_scoring.py` | Create | Server scoring/apply integration tests |

---

## Task 1: Dependencies and Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `.env`

- [ ] **Step 1: Update requirements.txt**

Remove `pdfplumber` and add new dependencies:

```
mcp>=1.0.0
httpx>=0.27.0
playwright>=1.40.0
reportlab>=4.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
aiosqlite>=0.20.0
scikit-learn>=1.4.0
pyyaml>=6.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Install new dependencies**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/pip install scikit-learn pyyaml`
Expected: Successfully installed

- [ ] **Step 3: Update .env (local only, not committed)**

Append to existing `.env`:

```env
MASTER_RESUME_YAML=~/.naukri-mcp/master_resume.yaml
MIN_MATCH_SCORE=0.50
TARGET_ATS_SCORE=0.70
MAX_TAILOR_ITERATIONS=3
SCORE_KEYWORD_WEIGHT=0.6
```

- [ ] **Step 4: Update .env.example with new variable names (no values)**

Append to `.env.example`:

```env
# Scoring and tailoring config
MASTER_RESUME_YAML=~/.naukri-mcp/master_resume.yaml
MIN_MATCH_SCORE=0.50
TARGET_ATS_SCORE=0.70
MAX_TAILOR_ITERATIONS=3
SCORE_KEYWORD_WEIGHT=0.6
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add scikit-learn, pyyaml deps; remove pdfplumber; add scoring config to .env.example"
```

---

## Task 2: Pydantic Models (`models.py`)

**Files:**
- Modify: `models.py:1-43`
- Test: `tests/test_models_scoring.py`

- [ ] **Step 1: Write failing tests for new models**

Create `tests/test_models_scoring.py`:

```python
from datetime import datetime
import pytest
from models import ResumeScore, ResumeVersion, MasterResume


def test_resume_score_fields():
    score = ResumeScore(
        overall_score=0.65,
        keyword_score=0.7,
        tfidf_score=0.55,
        matched_skills=["Node.js", "Kafka"],
        missing_skills=["Python"],
        gap_analysis="Moderate match. Matched: Node.js, Kafka. Missing: Python.",
        recommendation="tailor",
    )
    assert score.overall_score == 0.65
    assert score.recommendation == "tailor"
    assert len(score.matched_skills) == 2
    assert "Python" in score.missing_skills


def test_resume_score_recommendation_values():
    for rec in ["skip", "tailor", "apply_directly"]:
        score = ResumeScore(
            overall_score=0.5, keyword_score=0.5, tfidf_score=0.5,
            matched_skills=[], missing_skills=[],
            gap_analysis="test", recommendation=rec,
        )
        assert score.recommendation == rec


def test_resume_version_fields():
    version = ResumeVersion(
        id="J001_v1",
        job_id="J001",
        iteration=1,
        file_path="/tmp/resume.pdf",
        score_before=0.45,
        score_after=0.72,
        selected_achievements=["pri-xneeti-arch", "hkb-streaming"],
        created_at=datetime.now(),
    )
    assert version.id == "J001_v1"
    assert version.iteration == 1
    assert len(version.selected_achievements) == 2


def test_resume_version_optional_scores():
    version = ResumeVersion(
        id="J001_v1", job_id="J001", iteration=1,
        file_path="/tmp/resume.pdf", created_at=datetime.now(),
    )
    assert version.score_before is None
    assert version.score_after is None
    assert version.selected_achievements == []


def test_master_resume_validation():
    data = {
        "meta": {"name": "Test", "email": "test@test.com", "phone": "1234567890"},
        "summary": {"default": "A developer.", "variants": {"backend": "Backend dev."}},
        "skills": [{"category": "Languages", "items": ["Python"]}],
        "experience": [{"company": "Co", "role": "Dev", "dates": "2020-2024", "achievements": []}],
    }
    resume = MasterResume(**data)
    assert resume.meta["name"] == "Test"
    assert len(resume.skills) == 1


def test_master_resume_optional_fields():
    data = {
        "meta": {"name": "Test", "email": "t@t.com", "phone": "123"},
        "summary": {"default": "Dev.", "variants": {}},
        "skills": [{"category": "Lang", "items": ["JS"]}],
        "experience": [{"company": "Co", "role": "Dev", "dates": "2024", "achievements": []}],
    }
    resume = MasterResume(**data)
    assert resume.projects == []
    assert resume.education == []
    assert resume.certifications == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_models_scoring.py -v`
Expected: FAIL — `ImportError: cannot import name 'ResumeScore' from 'models'`

- [ ] **Step 3: Add models to models.py**

Append after the `NaukriProfile` class (after line 43):

```python
class ResumeScore(BaseModel):
    overall_score: float
    keyword_score: float
    tfidf_score: float
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    gap_analysis: str
    recommendation: str  # "skip" | "tailor" | "apply_directly"


class ResumeVersion(BaseModel):
    id: str  # Format: "{job_id}_v{iteration}"
    job_id: str
    iteration: int
    file_path: str
    score_before: float | None = None
    score_after: float | None = None
    selected_achievements: list[str] = Field(default_factory=list)
    created_at: datetime


class MasterResume(BaseModel):
    """Pydantic validator for master_resume.yaml schema."""
    meta: dict  # Required: name, email, phone
    summary: dict  # Required: default, variants
    skills: list[dict]  # Required: at least one category
    experience: list[dict]  # Required: at least one entry
    projects: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    certifications: list[dict] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_models_scoring.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run all existing tests to verify no regressions**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_models.py -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add models.py tests/test_models_scoring.py
git commit -m "feat: add ResumeScore, ResumeVersion, MasterResume pydantic models"
```

---

## Task 3: Test Fixtures

**Files:**
- Create: `tests/fixtures/sample_resume.yaml`
- Create: `tests/fixtures/sample_jd.txt`
- Create: `tests/fixtures/sample_jd_poor_match.txt`

- [ ] **Step 1: Create sample resume YAML fixture**

Create `tests/fixtures/sample_resume.yaml`:

```yaml
meta:
  name: "Test User"
  email: "test@example.com"
  phone: "+91-1234567890"
  location: "Bangalore, India"

summary:
  default: "Senior Software Engineer with 4+ years building scalable backend systems using Node.js, TypeScript, PostgreSQL, Kafka, and AWS."
  variants:
    backend: "Backend engineer specializing in distributed systems and real-time data processing."
    fullstack: "Full-stack developer with deep backend expertise and React.js frontend experience."

skills:
  - category: "Languages"
    items: ["JavaScript", "TypeScript", "SQL"]
  - category: "Frameworks"
    items: ["NestJS", "Node.js", "Express.js", "React.js"]
  - category: "Infrastructure"
    items: ["Docker", "AWS", "Kafka", "Redis", "PostgreSQL", "MongoDB"]

experience:
  - company: "Acme Corp"
    role: "SDE II"
    dates: "2023 - Present"
    location: "Remote"
    achievements:
      - id: "acme-kafka"
        text: "Built real-time data pipeline processing 10M events/day using Kafka and Node.js."
        tags: ["kafka", "node.js", "data-pipeline", "real-time", "backend"]
      - id: "acme-microservices"
        text: "Led migration from monolith to microservices architecture using NestJS and Docker."
        tags: ["microservices", "nestjs", "docker", "architecture", "leadership"]
      - id: "acme-aws"
        text: "Deployed services on AWS with auto-scaling, reducing infra costs by 30%."
        tags: ["aws", "devops", "scalability", "cost-optimization"]
  - company: "Startup Inc"
    role: "Backend Developer"
    dates: "2021 - 2023"
    location: "Bangalore"
    achievements:
      - id: "startup-api"
        text: "Developed REST APIs serving 50k req/min using Express.js and PostgreSQL."
        tags: ["express.js", "postgresql", "api", "performance", "backend"]
      - id: "startup-redis"
        text: "Implemented Redis caching layer reducing response times by 60%."
        tags: ["redis", "caching", "performance", "backend"]

projects:
  - name: "Chat App"
    tech: ["Node.js", "Socket.io", "React"]
    achievements:
      - id: "proj-chat"
        text: "Built real-time chat with Socket.io supporting 10k concurrent connections."
        tags: ["socket.io", "real-time", "websocket", "node.js"]

education:
  - degree: "B.Tech Computer Science"
    institution: "Test University"
    dates: "2017 - 2021"
```

- [ ] **Step 2: Create good-match JD fixture**

Create `tests/fixtures/sample_jd.txt`:

```
Senior Backend Engineer

We are looking for a Senior Backend Engineer to join our platform team.

Requirements:
- 4+ years of experience with Node.js and TypeScript
- Strong experience with PostgreSQL and Redis
- Experience with Kafka or similar message queue systems
- Familiarity with Docker and AWS (EC2, S3, SQS)
- Experience building microservices architecture
- Knowledge of NestJS framework preferred
- Experience with real-time data processing

Nice to have:
- Experience with Kubernetes
- GraphQL knowledge
- CI/CD pipeline experience

Responsibilities:
- Design and build scalable backend services
- Optimize database queries and caching strategies
- Collaborate with frontend and DevOps teams
```

- [ ] **Step 3: Create poor-match JD fixture**

Create `tests/fixtures/sample_jd_poor_match.txt`:

```
Senior iOS Developer

We are looking for a Senior iOS Developer to build our mobile application.

Requirements:
- 5+ years of experience with Swift and Objective-C
- Strong experience with UIKit and SwiftUI
- Experience with Core Data and Realm databases
- Familiarity with Xcode and Instruments profiling
- Experience with App Store submission process
- Knowledge of MVVM and Clean Architecture patterns

Nice to have:
- Experience with Flutter or React Native
- AR/VR development experience
- Machine Learning on-device experience
```

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/
git commit -m "test: add sample resume YAML, good-match JD, and poor-match JD fixtures"
```

---

## Task 4: Resume Scorer (`resume_scorer.py`)

**Files:**
- Create: `resume_scorer.py`
- Test: `tests/test_resume_scorer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_resume_scorer.py`:

```python
import os
import pytest
from pathlib import Path
from resume_scorer import ResumeScorer
from models import ResumeScore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def scorer():
    return ResumeScorer(str(FIXTURES / "sample_resume.yaml"))


@pytest.fixture
def good_jd():
    return (FIXTURES / "sample_jd.txt").read_text()


@pytest.fixture
def poor_jd():
    return (FIXTURES / "sample_jd_poor_match.txt").read_text()


def test_scorer_loads_yaml(scorer):
    assert scorer.resume_data is not None
    assert scorer.resume_data["meta"]["name"] == "Test User"
    assert len(scorer.all_skills) > 0
    assert len(scorer.all_tags) > 0


def test_scorer_extracts_skills_from_yaml(scorer):
    # Skills should include items from all categories
    assert "Node.js" in scorer.all_skills
    assert "PostgreSQL" in scorer.all_skills
    assert "Docker" in scorer.all_skills


def test_scorer_extracts_tags_from_yaml(scorer):
    # Tags come from achievement tags
    assert "kafka" in scorer.all_tags
    assert "microservices" in scorer.all_tags
    assert "redis" in scorer.all_tags


def test_score_good_match(scorer, good_jd):
    result = scorer.score(good_jd)
    assert isinstance(result, ResumeScore)
    assert result.overall_score >= 0.50
    assert result.recommendation in ("tailor", "apply_directly")
    assert len(result.matched_skills) > 0
    assert "Node.js" in result.matched_skills or "node.js" in [s.lower() for s in result.matched_skills]


def test_score_poor_match(scorer, poor_jd):
    result = scorer.score(poor_jd)
    assert isinstance(result, ResumeScore)
    assert result.overall_score < 0.50
    assert result.recommendation == "skip"
    assert len(result.missing_skills) > len(result.matched_skills)


def test_score_returns_gap_analysis(scorer, good_jd):
    result = scorer.score(good_jd)
    assert isinstance(result.gap_analysis, str)
    assert len(result.gap_analysis) > 0
    # Should mention match quality
    assert any(word in result.gap_analysis.lower() for word in ["match", "matched", "missing"])


def test_score_with_tailored_text(scorer, good_jd):
    tailored = """
    Senior Backend Engineer with 4+ years experience in Node.js, TypeScript, PostgreSQL, Redis, Kafka.
    Built microservices with NestJS and Docker on AWS. Real-time data processing expert.
    """
    result = scorer.score(good_jd, tailored_text=tailored)
    assert isinstance(result, ResumeScore)
    # Tailored text should score at least as well as master
    master_result = scorer.score(good_jd)
    assert result.overall_score >= master_result.overall_score - 0.1  # some tolerance


def test_extract_jd_keywords_handles_compound_terms(scorer):
    jd = "We need experience with Node.js, React.js, and AWS S3."
    keywords = scorer._extract_jd_keywords(jd)
    # Should find compound terms as units
    assert any("node" in k.lower() for k in keywords)


def test_score_keyword_and_tfidf_both_populated(scorer, good_jd):
    result = scorer.score(good_jd)
    assert 0.0 <= result.keyword_score <= 1.0
    assert 0.0 <= result.tfidf_score <= 1.0
    assert 0.0 <= result.overall_score <= 1.0


def test_scorer_missing_yaml_raises_error():
    with pytest.raises(FileNotFoundError):
        ResumeScorer("/nonexistent/path/resume.yaml")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_resume_scorer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'resume_scorer'`

- [ ] **Step 3: Implement resume_scorer.py**

Create `resume_scorer.py`:

```python
import os
import re
from pathlib import Path

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from models import ResumeScore, MasterResume


# Common tech terms dictionary (seed list — augmented by YAML skills/tags at runtime)
BASE_TECH_TERMS = {
    "python", "javascript", "typescript", "java", "go", "golang", "rust", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "scala", "sql", "html", "css", "html/css",
    "node.js", "react.js", "react", "angular", "vue.js", "vue", "next.js", "nuxt.js",
    "express.js", "express", "nestjs", "fastapi", "django", "flask", "spring", "spring boot",
    "rails", "laravel", ".net", "asp.net",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb", "cassandra",
    "sqlite", "oracle", "sql server",
    "kafka", "rabbitmq", "bullmq", "sqs", "sns", "eventbridge", "nats",
    "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins", "github actions",
    "ci/cd", "aws", "gcp", "azure", "firebase", "heroku", "vercel",
    "s3", "ec2", "lambda", "ecs", "eks", "fargate", "cloudfront",
    "graphql", "rest", "rest api", "grpc", "websocket", "socket.io", "webrtc",
    "microservices", "monolith", "serverless", "event-driven",
    "redux", "zustand", "tailwindcss", "tailwind", "material ui", "bootstrap",
    "jest", "mocha", "pytest", "cypress", "playwright", "selenium",
    "git", "postman", "swagger", "openapi",
    "typeorm", "prisma", "sequelize", "mongoose", "sqlalchemy",
    "jwt", "oauth", "saml", "sso",
    "nginx", "apache", "caddy", "load balancing",
    "zod", "joi", "pydantic",
    "machine learning", "deep learning", "nlp", "computer vision",
    "agile", "scrum", "kanban", "jira", "confluence",
}


class ResumeScorer:
    """Local keyword + TF-IDF scoring engine for resume-JD matching."""

    def __init__(self, yaml_path: str):
        """Load master resume YAML. Raises FileNotFoundError if missing."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(
                f"master_resume.yaml not found at {yaml_path}. "
                f"Create it at ~/.naukri-mcp/master_resume.yaml"
            )

        with open(path) as f:
            raw = yaml.safe_load(f)

        # Validate schema
        self.resume_data = raw
        MasterResume(**raw)  # raises ValidationError if invalid

        # Extract all skills (from skills.items, flattened, lowercased)
        self.all_skills: set[str] = set()
        for cat in raw.get("skills", []):
            for item in cat.get("items", []):
                self.all_skills.add(item)
                self.all_skills.add(item.lower())

        # Extract all tags (from achievements across experience + projects)
        self.all_tags: set[str] = set()
        for section in ("experience", "projects"):
            for entry in raw.get(section, []):
                for ach in entry.get("achievements", []):
                    for tag in ach.get("tags", []):
                        self.all_tags.add(tag.lower())

        # Build the full tech dictionary (base + YAML skills + tags)
        self._tech_dict: set[str] = BASE_TECH_TERMS | {s.lower() for s in self.all_skills} | self.all_tags

        # Pre-build resume text for master scoring
        self._master_text = self._build_resume_text(raw)

        # Configurable weights
        self._keyword_weight = float(os.getenv("SCORE_KEYWORD_WEIGHT", "0.6"))

    def score(self, jd_text: str, tailored_text: str | None = None) -> ResumeScore:
        """Score resume against JD. If tailored_text provided, score that instead."""
        resume_text = tailored_text or self._master_text

        # Layer 1: Keyword matching
        jd_keywords = self._extract_jd_keywords(jd_text)
        resume_keywords = self._extract_jd_keywords(resume_text)
        matched = jd_keywords & resume_keywords
        keyword_score = len(matched) / max(len(jd_keywords), 1)

        # Layer 2: TF-IDF cosine similarity
        tfidf_score = self._tfidf_similarity(resume_text, jd_text)

        # Combined score
        tfidf_weight = 1.0 - self._keyword_weight
        overall = self._keyword_weight * keyword_score + tfidf_weight * tfidf_score

        # Gap analysis
        missing = jd_keywords - resume_keywords
        gap_analysis = self._build_gap_analysis(list(matched), list(missing))

        return ResumeScore(
            overall_score=round(overall, 4),
            keyword_score=round(keyword_score, 4),
            tfidf_score=round(tfidf_score, 4),
            matched_skills=sorted(matched),
            missing_skills=sorted(missing),
            gap_analysis=gap_analysis,
            recommendation=self._recommend(overall),
        )

    def _extract_jd_keywords(self, text: str) -> set[str]:
        """Extract tech skills/tools from text using dictionary matching.

        Strategy:
        1. Normalize text to lowercase
        2. Handle parenthetical expansions: "AWS (S3, EC2)" -> "aws", "s3", "ec2"
        3. Match against tech dictionary using word-boundary-aware matching
        4. Return matched terms in lowercase canonical form
        """
        normalized = text.lower()

        # Expand parentheticals: "AWS (S3, EC2, KMS)" -> adds s3, ec2, kms
        paren_pattern = re.compile(r'\(([^)]+)\)')
        for match in paren_pattern.finditer(normalized):
            inner = match.group(1)
            for part in re.split(r'[,;/]', inner):
                part = part.strip()
                if part:
                    normalized += f" {part}"

        found: set[str] = set()
        for term in self._tech_dict:
            # Use word boundary for short terms, substring for compound terms
            if len(term) <= 2:
                # Very short terms (e.g., "go", "c#") — need exact word boundary
                pattern = r'\b' + re.escape(term) + r'\b'
            elif '.' in term or '/' in term or '+' in term or '#' in term:
                # Compound terms like "node.js", "c++", "c#", "ci/cd"
                if term in normalized:
                    found.add(term)
                continue
            else:
                pattern = r'\b' + re.escape(term) + r'\b'

            if re.search(pattern, normalized):
                found.add(term)

        return found

    def _tfidf_similarity(self, text_a: str, text_b: str) -> float:
        """TF-IDF vectorization + cosine similarity between two texts."""
        try:
            tfidf = TfidfVectorizer(stop_words='english', min_df=1)
            matrix = tfidf.fit_transform([text_a, text_b])
            sim = cosine_similarity(matrix[0:1], matrix[1:2])[0][0]
            return float(sim)
        except ValueError:
            # Empty vocabulary (e.g., both texts are stop words only)
            return 0.0

    def _recommend(self, score: float) -> str:
        min_score = float(os.getenv("MIN_MATCH_SCORE", "0.50"))
        target_score = float(os.getenv("TARGET_ATS_SCORE", "0.70"))
        if score < min_score:
            return "skip"
        elif score >= target_score:
            return "apply_directly"
        else:
            return "tailor"

    def _build_gap_analysis(self, matched: list[str], missing: list[str]) -> str:
        """Generate human-readable gap analysis."""
        parts = []
        total = len(matched) + len(missing)
        ratio = len(matched) / max(total, 1)

        if ratio >= 0.7:
            parts.append("Strong match.")
        elif ratio >= 0.5:
            parts.append("Moderate match.")
        else:
            parts.append("Weak match.")

        if matched:
            parts.append(f"Matched: {', '.join(matched[:5])}")
            if len(matched) > 5:
                parts[-1] += f" (+{len(matched) - 5} more)"
        if missing:
            parts.append(f"Missing: {', '.join(missing[:5])}")
            if len(missing) > 5:
                parts[-1] += f" (+{len(missing) - 5} more)"

        return " ".join(parts)

    def _build_resume_text(self, data: dict) -> str:
        """Build a flat text representation of the YAML resume for TF-IDF."""
        parts = []
        parts.append(data.get("summary", {}).get("default", ""))
        for cat in data.get("skills", []):
            parts.append(" ".join(cat.get("items", [])))
        for exp in data.get("experience", []):
            parts.append(f"{exp.get('role', '')} at {exp.get('company', '')}")
            for ach in exp.get("achievements", []):
                parts.append(ach.get("text", ""))
        for proj in data.get("projects", []):
            parts.append(proj.get("name", ""))
            for ach in proj.get("achievements", []):
                parts.append(ach.get("text", ""))
        return " ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_resume_scorer.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add resume_scorer.py tests/test_resume_scorer.py
git commit -m "feat: add resume scoring engine with keyword + TF-IDF matching"
```

---

## Task 5: Tracker — Resume Versions Table (`tracker.py`)

**Files:**
- Modify: `tracker.py:17-37` (init method) and append new methods
- Test: `tests/test_tracker_versions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tracker_versions.py`:

```python
import json
from datetime import datetime
import pytest
import pytest_asyncio
from models import Job, ResumeVersion
from tracker import JobTracker


@pytest_asyncio.fixture
async def tracker(tmp_path):
    db_path = str(tmp_path / "test_jobs.db")
    t = JobTracker(db_path=db_path)
    await t.init()
    # Seed a job for FK references
    job = Job(
        id="J001", title="Python Dev", company="Flipkart",
        location="Bangalore", skills_required=["Python"],
        url="https://naukri.com/job/J001", found_at=datetime.now(),
        status="approved",
    )
    await t.save_job(job)
    yield t
    await t.close()


async def test_save_and_get_resume_version(tracker):
    version = ResumeVersion(
        id="J001_v1", job_id="J001", iteration=1,
        file_path="/tmp/J001_v1.pdf",
        score_before=0.45, score_after=0.68,
        selected_achievements=["acme-kafka", "acme-aws"],
        created_at=datetime.now(),
    )
    await tracker.save_resume_version(version)
    versions = await tracker.get_resume_versions("J001")
    assert len(versions) == 1
    assert versions[0].id == "J001_v1"
    assert versions[0].score_after == 0.68
    assert versions[0].selected_achievements == ["acme-kafka", "acme-aws"]


async def test_get_best_resume(tracker):
    for i, score in enumerate([0.55, 0.72, 0.65], 1):
        v = ResumeVersion(
            id=f"J001_v{i}", job_id="J001", iteration=i,
            file_path=f"/tmp/J001_v{i}.pdf",
            score_before=0.45, score_after=score,
            selected_achievements=[], created_at=datetime.now(),
        )
        await tracker.save_resume_version(v)
    best = await tracker.get_best_resume("J001")
    assert best is not None
    assert best.id == "J001_v2"  # score 0.72 is highest
    assert best.score_after == 0.72


async def test_get_best_resume_no_versions(tracker):
    best = await tracker.get_best_resume("J999")
    assert best is None


async def test_get_iteration_count(tracker):
    assert await tracker.get_iteration_count("J001") == 0
    for i in range(1, 4):
        v = ResumeVersion(
            id=f"J001_v{i}", job_id="J001", iteration=i,
            file_path=f"/tmp/v{i}.pdf",
            created_at=datetime.now(),
        )
        await tracker.save_resume_version(v)
    assert await tracker.get_iteration_count("J001") == 3


async def test_get_application_stats(tracker):
    # Save another job as applied
    job2 = Job(
        id="J002", title="Node Dev", company="Swiggy",
        location="Mumbai", skills_required=["Node.js"],
        url="https://naukri.com/job/J002", found_at=datetime.now(),
        status="applied",
    )
    await tracker.save_job(job2)
    await tracker.mark_applied("J002", "/tmp/resume.pdf")

    # Save a version for J002
    v = ResumeVersion(
        id="J002_v1", job_id="J002", iteration=1,
        file_path="/tmp/J002_v1.pdf",
        score_before=0.55, score_after=0.72,
        selected_achievements=[], created_at=datetime.now(),
    )
    await tracker.save_resume_version(v)

    stats = await tracker.get_application_stats()
    assert "applied" in stats
    assert stats["applied"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_tracker_versions.py -v`
Expected: FAIL — `AttributeError: 'JobTracker' object has no attribute 'save_resume_version'`

- [ ] **Step 3: Add resume_versions table to init()**

In `tracker.py`, after the existing `CREATE TABLE IF NOT EXISTS jobs` block (after line 37, before `await self._conn.commit()`), add:

```python
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS resume_versions (
                id                    TEXT PRIMARY KEY,
                job_id                TEXT NOT NULL,
                iteration             INTEGER NOT NULL,
                file_path             TEXT NOT NULL,
                score_before          REAL,
                score_after           REAL,
                selected_achievements TEXT,
                created_at            DATETIME NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)
```

- [ ] **Step 4: Add new methods to JobTracker**

Append to `tracker.py` before the `_row_to_job` method (before line 111):

```python
    async def save_resume_version(self, version: ResumeVersion) -> None:
        await self._conn.execute("""
            INSERT OR REPLACE INTO resume_versions
                (id, job_id, iteration, file_path, score_before, score_after,
                 selected_achievements, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            version.id, version.job_id, version.iteration, version.file_path,
            version.score_before, version.score_after,
            json.dumps(version.selected_achievements),
            version.created_at.isoformat(),
        ))
        await self._conn.commit()

    async def get_resume_versions(self, job_id: str) -> list[ResumeVersion]:
        async with self._conn.execute(
            "SELECT * FROM resume_versions WHERE job_id = ? ORDER BY iteration",
            (job_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_version(r) for r in rows]

    async def get_best_resume(self, job_id: str) -> ResumeVersion | None:
        async with self._conn.execute(
            "SELECT * FROM resume_versions WHERE job_id = ? ORDER BY score_after DESC LIMIT 1",
            (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_version(row) if row else None

    async def get_iteration_count(self, job_id: str) -> int:
        async with self._conn.execute(
            "SELECT COUNT(*) FROM resume_versions WHERE job_id = ?", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_application_stats(self) -> dict:
        stats = {}
        # Count by status
        async with self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            stats[row["status"]] = row["cnt"]

        # Average scores from resume_versions
        async with self._conn.execute("""
            SELECT
                COUNT(*) as total_versions,
                AVG(score_before) as avg_initial_score,
                AVG(score_after) as avg_final_score,
                AVG(iteration) as avg_iterations
            FROM resume_versions
        """) as cursor:
            row = await cursor.fetchone()
        if row and row["total_versions"]:
            stats["total_versions"] = row["total_versions"]
            stats["avg_initial_score"] = round(row["avg_initial_score"] or 0, 4)
            stats["avg_final_score"] = round(row["avg_final_score"] or 0, 4)
            stats["avg_iterations"] = round(row["avg_iterations"] or 0, 1)

        return stats

    def _row_to_version(self, row) -> ResumeVersion:
        data = dict(row)
        return ResumeVersion(
            id=data["id"],
            job_id=data["job_id"],
            iteration=data["iteration"],
            file_path=data["file_path"],
            score_before=data.get("score_before"),
            score_after=data.get("score_after"),
            selected_achievements=json.loads(data.get("selected_achievements") or "[]"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
```

Also add the import at the top of `tracker.py`:

```python
from models import Job, ResumeVersion
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_tracker_versions.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Run existing tracker tests for regression**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_tracker.py -v`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
git add tracker.py tests/test_tracker_versions.py
git commit -m "feat: add resume_versions table with save, get_best, iteration_count, stats"
```

---

## Task 6: Enhanced Resume Tailor (`resume_tailor.py`)

**Files:**
- Modify: `resume_tailor.py` (full rewrite)
- Test: `tests/test_resume_tailor_v2.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_resume_tailor_v2.py`:

```python
import os
from pathlib import Path
import pytest
import pytest_asyncio
from resume_tailor import ResumeTailor

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tailor(tmp_path):
    return ResumeTailor(output_dir=str(tmp_path))


def test_load_yaml(tailor):
    data = tailor.load_yaml(str(FIXTURES / "sample_resume.yaml"))
    assert data["meta"]["name"] == "Test User"
    assert len(data["skills"]) > 0


def test_load_yaml_missing_file(tailor):
    with pytest.raises(FileNotFoundError):
        tailor.load_yaml("/nonexistent/resume.yaml")


@pytest.mark.asyncio
async def test_generate_pdf_creates_file(tailor):
    text = """PROFESSIONAL SUMMARY
Senior Backend Engineer with 4+ years of experience.

TECHNICAL SKILLS
Languages: JavaScript, TypeScript, Python
Frameworks: NestJS, Express.js, React.js

WORK EXPERIENCE
SDE II at Acme Corp (2023 - Present)
- Built real-time data pipeline processing 10M events/day using Kafka.
- Led migration from monolith to microservices architecture.

EDUCATION
B.Tech Computer Science, Test University (2017 - 2021)
"""
    path = await tailor.generate_pdf(text, "J001")
    assert os.path.exists(path)
    assert path.endswith(".pdf")
    assert os.path.getsize(path) > 0


@pytest.mark.asyncio
async def test_generate_pdf_handles_html_entities(tailor):
    """Ensure text with <, >, & doesn't break PDF generation."""
    text = """SKILLS
C++ & C#, Node.js <latest>, R&D experience
- Used AT&T APIs for <real-time> data processing
"""
    path = await tailor.generate_pdf(text, "J002")
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0


@pytest.mark.asyncio
async def test_generate_pdf_unique_filenames(tailor):
    path1 = await tailor.generate_pdf("Resume v1", "J001")
    path2 = await tailor.generate_pdf("Resume v2", "J001")
    assert path1 != path2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_resume_tailor_v2.py -v`
Expected: FAIL — `AttributeError: 'ResumeTailor' object has no attribute 'load_yaml'`

- [ ] **Step 3: Rewrite resume_tailor.py**

Replace the entire contents of `resume_tailor.py`:

```python
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import yaml
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from models import MasterResume

load_dotenv()


class ResumeTailor:
    """
    Handles YAML resume loading and ATS-optimized PDF generation.
    Resume tailoring (AI rewriting) is done by Claude Code itself.
    """

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(
            output_dir or os.path.expanduser(
                os.getenv("RESUME_OUTPUT_DIR", "~/.naukri-mcp/resumes")
            )
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.chmod(0o700)

    def load_yaml(self, yaml_path: str) -> dict:
        """Load and validate structured resume data from YAML.
        Raises FileNotFoundError if missing, ValidationError if malformed.
        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(
                f"master_resume.yaml not found at {yaml_path}. "
                f"Create it at ~/.naukri-mcp/master_resume.yaml"
            )
        with open(path) as f:
            data = yaml.safe_load(f)
        MasterResume(**data)  # validate schema
        return data

    async def generate_pdf(self, tailored_text: str, job_id: str) -> str:
        """Generate an ATS-optimized PDF with section hierarchy.

        - Detects headings (UPPERCASE lines or lines ending with ':')
        - Formats bullet points (lines starting with '- ' or '* ')
        - Escapes HTML entities for ReportLab safety
        - Uses ATS-safe Helvetica font, 10-12pt
        - Contact info in body (never header/footer)
        """
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

        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=12,
            spaceAfter=6,
            spaceBefore=12,
            textColor=black,
        )

        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            spaceAfter=3,
        )

        bullet_style = ParagraphStyle(
            'Bullet',
            parent=body_style,
            bulletIndent=12,
            leftIndent=24,
        )

        story = []
        for line in tailored_text.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 6))
            elif self._is_heading(line):
                story.append(Paragraph(escape(line), heading_style))
            elif line.startswith('- ') or line.startswith('* '):
                bullet_text = escape(line.lstrip('-* ').strip())
                story.append(
                    Paragraph(f'<bullet>&bull;</bullet>{bullet_text}', bullet_style)
                )
            else:
                story.append(Paragraph(escape(line), body_style))

        doc.build(story)
        return output_path

    def _is_heading(self, line: str) -> bool:
        """Detect section headings: all-uppercase or ending with ':'."""
        stripped = line.rstrip(':')
        if stripped.isupper() and len(stripped) > 2:
            return True
        if line.endswith(':') and not line.startswith('-'):
            return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_resume_tailor_v2.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run existing resume tailor tests (expect failures)**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_resume_tailor.py -v`
Expected: **WILL FAIL** — old tests reference `extract_text()` which is removed. This is expected and is fixed in Task 7 (Update Old Test Files), which runs immediately after this task.

- [ ] **Step 6: Commit**

```bash
git add resume_tailor.py tests/test_resume_tailor_v2.py
git commit -m "feat: rewrite resume_tailor with YAML loading, ATS-optimized PDF, HTML escaping"
```

---

## Task 7: Update Old Test Files (must run before server changes)

**Files:**
- Modify: `tests/test_resume_tailor.py` (remove extract_text tests)

- [ ] **Step 1: Check what existing resume tailor tests reference**

Read `tests/test_resume_tailor.py` and remove any tests that call `extract_text()` since that method is removed. Keep any `generate_pdf` tests (signature unchanged: `(tailored_text, job_id)`). Also remove the `import pdfplumber` if present.

- [ ] **Step 2: Run full test suite to confirm clean state**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_resume_tailor.py
git commit -m "test: remove extract_text tests (method removed in YAML migration)"
```

---

## Task 8: Master Resume YAML

**Files:**
- Create: `~/.naukri-mcp/master_resume.yaml`

- [ ] **Step 1: Create the master resume YAML**

Write the full YAML from the spec (Section 5) to `~/.naukri-mcp/master_resume.yaml`. This is Navjeet's actual resume data, already defined in the spec document at `docs/superpowers/specs/2026-03-21-ai-enhanced-job-pipeline-design.md`, Section 5. Copy the YAML block from lines 78-212 of the spec.

- [ ] **Step 2: Verify it loads**

```bash
cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -c "
import os
from resume_scorer import ResumeScorer
s = ResumeScorer(os.path.expanduser('~/.naukri-mcp/master_resume.yaml'))
print(f'Loaded {len(s.all_skills)} skills, {len(s.all_tags)} tags')
"
```

Expected: `Loaded XX skills, XX tags` (no errors)

- [ ] **Step 3: No git commit** — this file is in `~/.naukri-mcp/` (user data dir), not in the repo.

---

## Task 9: Server — New and Modified MCP Tools (`server.py`)

> **Note:** This task depends on Tasks 2-7 being complete (models, scorer, tracker, tailor, old tests fixed, master YAML created).

**Files:**
- Modify: `server.py` (all sections)

This is the largest task. It modifies imports, `__init__`, adds 3 new methods, modifies 2 existing methods, updates `list_tools`, and updates `call_tool`.

- [ ] **Step 1: Update imports at top of server.py (lines 1-14)**

Replace the import block:

```python
import asyncio
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from models import Job, ApplicationResult, ResumeVersion
from naukri import NaukriClient as NaukriBrowser, NaukriError, CaptchaError, LoginError, OTPRequiredError
from resume_tailor import ResumeTailor
from resume_scorer import ResumeScorer
from tracker import JobTracker
```

- [ ] **Step 2: Update NaukriMCPServer.__init__ (lines 22-29)**

Replace the `__init__` method:

```python
    def __init__(self):
        self.tracker = JobTracker()
        self.browser = NaukriBrowser(
            max_applications=int(os.getenv("MAX_APPLICATIONS_PER_SESSION", "50")),
        )
        self.tailor = ResumeTailor()
        self.base_resume_path = os.path.expanduser(os.getenv("BASE_RESUME_PATH", "./resume_base.pdf"))
        self.yaml_path = os.path.expanduser(os.getenv("MASTER_RESUME_YAML", "~/.naukri-mcp/master_resume.yaml"))
        self.scorer: ResumeScorer | None = None  # lazy-init on first score call
        self.max_iterations = int(os.getenv("MAX_TAILOR_ITERATIONS", "3"))
        self._started = False
```

- [ ] **Step 3: Replace _get_resume_data method (lines 92-124)**

```python
    async def _get_resume_data(self, job_id: str) -> dict:
        """
        Returns structured YAML resume data + job description + current score
        so Claude can tailor the resume. After tailoring, call generate_resume.
        """
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}

        # Load YAML
        try:
            resume_data = self.tailor.load_yaml(self.yaml_path)
        except FileNotFoundError as e:
            return {"error": str(e)}

        # Get JD
        detail = await self.browser.get_job_details(job_id, job.url)
        jd = detail.description if detail else job.title

        # Get current score
        scorer = self._get_scorer()
        current_score = scorer.score(jd) if scorer else None

        # Derive iteration from DB
        iteration = await self.tracker.get_iteration_count(job_id) + 1

        return {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "job_description": jd,
            "resume_data": resume_data,
            "current_score": current_score.model_dump() if current_score else None,
            "iteration": iteration,
            "instructions": (
                "Select and reorder achievements from resume_data that best match "
                "the job_description. Use missing_skills from current_score to guide "
                "emphasis. Do NOT invent new achievements. You may adapt summary from "
                "variants. Reorder skill categories to front-load most relevant. "
                "Format output as plain text with sections: PROFESSIONAL SUMMARY, "
                "TECHNICAL SKILLS, WORK EXPERIENCE, PROJECTS, EDUCATION. "
                "Then call generate_resume with the tailored text."
            ),
        }
```

- [ ] **Step 4: Replace _generate_and_upload_resume with _generate_resume (lines 126-139)**

```python
    async def _generate_resume(self, job_id: str, tailored_text: str) -> dict:
        """Generate a PDF locally from Claude's tailored text. Does NOT upload."""
        try:
            resume_path = await self.tailor.generate_pdf(tailored_text, job_id)

            # Save version to DB
            iteration = await self.tracker.get_iteration_count(job_id) + 1
            version = ResumeVersion(
                id=f"{job_id}_v{iteration}",
                job_id=job_id,
                iteration=iteration,
                file_path=resume_path,
                created_at=datetime.now(),
            )
            await self.tracker.save_resume_version(version)

            return {
                "success": True,
                "resume_path": resume_path,
                "iteration": iteration,
                "message": "Resume generated locally. Call score_resume_match to verify score, then upload_and_apply when ready.",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "resume_path": None}
```

- [ ] **Step 5: Add new methods — _score_resume_match, _upload_and_apply, _get_application_stats, _get_scorer**

Add these after `_generate_resume`:

```python
    def _get_scorer(self) -> ResumeScorer | None:
        """Lazy-init scorer on first use."""
        if self.scorer is None:
            try:
                self.scorer = ResumeScorer(self.yaml_path)
            except FileNotFoundError:
                return None
        return self.scorer

    async def _score_resume_match(self, job_id: str, tailored_text: str | None = None) -> dict:
        """Score resume against job description."""
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}

        # Get JD (from detail or cached description)
        detail = await self.browser.get_job_details(job_id, job.url)
        jd = detail.description if detail else job.title

        scorer = self._get_scorer()
        if not scorer:
            return {"error": f"master_resume.yaml not found at {self.yaml_path}"}

        result = scorer.score(jd, tailored_text=tailored_text)

        # If scoring a tailored version, update the latest resume_version's score_after
        if tailored_text:
            versions = await self.tracker.get_resume_versions(job_id)
            if versions:
                latest = versions[-1]  # last by iteration order
                if latest.score_after is None:
                    latest.score_after = result.overall_score
                    await self.tracker.save_resume_version(latest)

        return result.model_dump()

    async def _upload_and_apply(self, job_id: str) -> dict:
        """Upload best-scoring resume to Naukri, then apply."""
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"success": False, "error": f"Job {job_id} not found"}

        if job.status != "approved":
            return {"success": False, "error": "Job must be approved before applying."}

        if await self.tracker.is_duplicate(job_id):
            return {"success": False, "error": f"Already applied to job {job_id}"}

        # Get best resume version (or use base resume)
        best = await self.tracker.get_best_resume(job_id)
        resume_path = best.file_path if best else self.base_resume_path

        # Upload resume to Naukri profile
        try:
            uploaded = await self.browser.upload_resume(resume_path)
            if not uploaded:
                return {
                    "success": False,
                    "error": "Resume upload failed. Applying with existing profile resume.",
                }
        except Exception as e:
            return {"success": False, "error": f"Upload failed: {e}"}

        # Apply
        try:
            result = await self.browser.apply_to_job(job.url, dry_run=False)
        except CaptchaError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}
        except NaukriError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}

        # Questionnaire required
        if isinstance(result, dict) and result.get("needs_questionnaire"):
            return result

        await self.tracker.mark_applied(job_id, resume_path)

        return ApplicationResult(
            job_id=job_id,
            success=bool(result),
            resume_used=resume_path,
            used_tailored_resume=best is not None,
            error=None if result else "Application button not found",
            applied_at=datetime.now(),
        ).model_dump(mode="json")

    async def _get_application_stats(self) -> dict:
        """Return session application statistics."""
        return {"session_stats": await self.tracker.get_application_stats()}
```

- [ ] **Step 6: Update list_tools() — add 3 new tools, rename generate_and_upload_resume**

In the `list_tools()` function, replace the `generate_and_upload_resume` tool entry with `generate_resume`, and add entries for `score_resume_match`, `upload_and_apply`, and `get_application_stats`:

Replace the `generate_and_upload_resume` Tool block (lines 269-280):

```python
        types.Tool(
            name="generate_resume",
            description="Generate a PDF from Claude's tailored resume text. Does NOT upload — call upload_and_apply after scoring.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "tailored_text": {"type": "string", "description": "The tailored resume as plain text"},
                },
                "required": ["job_id", "tailored_text"],
            },
        ),
```

Add these new tools to the list (before `apply_job`):

```python
        types.Tool(
            name="score_resume_match",
            description="Score resume against a job's description. Returns match score, matched/missing skills, and recommendation (skip/tailor/apply_directly). Call get_job_details first to fetch the JD.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "tailored_text": {"type": "string", "description": "Optional: score this text instead of master resume"},
                },
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="upload_and_apply",
            description="Upload the best-scoring resume version to Naukri and submit the application. Call after the score->tailor->score loop is complete.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="get_application_stats",
            description="Get session statistics: total scored, applied, skipped, average scores, average iterations.",
            inputSchema={"type": "object", "properties": {}},
        ),
```

- [ ] **Step 7: Update call_tool() dispatch — add new routes, rename old one**

In the `call_tool()` function, replace the `generate_and_upload_resume` route (lines 367-370):

```python
        elif name == "generate_resume":
            result = await s._generate_resume(
                arguments["job_id"], arguments["tailored_text"]
            )
```

Add new routes (before the `else` at end):

```python
        elif name == "score_resume_match":
            result = await s._score_resume_match(
                arguments["job_id"], arguments.get("tailored_text")
            )
        elif name == "upload_and_apply":
            result = await s._upload_and_apply(arguments["job_id"])
        elif name == "get_application_stats":
            result = await s._get_application_stats()
```

- [ ] **Step 8: Run all tests**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS (new and existing)

- [ ] **Step 9: Verify server loads without errors**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -c "from server import NaukriMCPServer; print('Server module loads OK')"`
Expected: `Server module loads OK`

- [ ] **Step 10: Commit**

```bash
git add server.py
git commit -m "feat: add score_resume_match, upload_and_apply, get_application_stats tools; refactor get_resume_data and generate_resume"
```

---

## Task 10: Server Integration Tests

**Files:**
- Create: `tests/test_server_scoring.py`

- [ ] **Step 1: Write server scoring tests**

Create `tests/test_server_scoring.py`. These tests mock the NaukriBrowser to avoid real browser calls and test the scoring/generation/stats flow:

```python
import os
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from models import Job, JobDetail
from server import NaukriMCPServer

FIXTURES = Path(__file__).parent / "fixtures"


@pytest_asyncio.fixture
async def server(tmp_path):
    """Create a server with mocked browser and test YAML."""
    with patch.dict(os.environ, {
        "MASTER_RESUME_YAML": str(FIXTURES / "sample_resume.yaml"),
        "RESUME_OUTPUT_DIR": str(tmp_path / "resumes"),
        "BASE_RESUME_PATH": str(tmp_path / "base.pdf"),
        "MIN_MATCH_SCORE": "0.50",
        "TARGET_ATS_SCORE": "0.70",
    }):
        s = NaukriMCPServer()
        s.tracker.db_path = str(tmp_path / "test.db")
        s.tracker = __import__("tracker").JobTracker(db_path=str(tmp_path / "test.db"))
        await s.tracker.init()

        # Mock browser
        s.browser = MagicMock()
        s.browser.get_job_details = AsyncMock(return_value=JobDetail(
            id="J001", title="Senior Node.js Developer", company="TestCo",
            location="Bangalore", url="https://naukri.com/job/J001",
            found_at=datetime.now(),
            description=(FIXTURES / "sample_jd.txt").read_text(),
            experience_required="4-6 years", posted_at="2 days ago",
        ))
        s.browser.upload_resume = AsyncMock(return_value=True)
        s.browser.apply_to_job = AsyncMock(return_value=True)
        s._started = True

        # Seed a job
        job = Job(
            id="J001", title="Senior Node.js Developer", company="TestCo",
            location="Bangalore", skills_required=["Node.js"],
            url="https://naukri.com/job/J001", found_at=datetime.now(),
            status="approved",
        )
        await s.tracker.save_job(job)

        yield s
        await s.tracker.close()


async def test_score_resume_match_returns_score(server):
    result = await server._score_resume_match("J001")
    assert "error" not in result
    assert "overall_score" in result
    assert result["overall_score"] > 0
    assert "matched_skills" in result
    assert "recommendation" in result


async def test_score_resume_match_good_jd_above_threshold(server):
    result = await server._score_resume_match("J001")
    assert result["overall_score"] >= 0.50
    assert result["recommendation"] in ("tailor", "apply_directly")


async def test_generate_resume_creates_version(server):
    tailored = "PROFESSIONAL SUMMARY\nSenior Node.js developer.\n\nSKILLS\nNode.js, Kafka"
    result = await server._generate_resume("J001", tailored)
    assert result["success"] is True
    assert result["iteration"] == 1
    assert os.path.exists(result["resume_path"])

    # Second generation increments iteration
    result2 = await server._generate_resume("J001", tailored + " v2")
    assert result2["iteration"] == 2


async def test_score_tailored_text_updates_version(server):
    # Generate first
    tailored = "Node.js Kafka PostgreSQL Redis microservices AWS Docker NestJS"
    await server._generate_resume("J001", tailored)

    # Score the tailored text
    result = await server._score_resume_match("J001", tailored_text=tailored)
    assert result["overall_score"] > 0

    # Check version was updated
    versions = await server.tracker.get_resume_versions("J001")
    assert len(versions) == 1
    assert versions[0].score_after is not None


async def test_get_resume_data_returns_yaml_and_score(server):
    result = await server._get_resume_data("J001")
    assert "error" not in result
    assert "resume_data" in result
    assert "current_score" in result
    assert "iteration" in result
    assert result["iteration"] == 1
    assert result["resume_data"]["meta"]["name"] == "Test User"


async def test_get_application_stats(server):
    result = await server._get_application_stats()
    assert "session_stats" in result
    stats = result["session_stats"]
    assert "approved" in stats


async def test_score_missing_job_returns_error(server):
    result = await server._score_resume_match("J999")
    assert "error" in result
```

- [ ] **Step 2: Run tests**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/test_server_scoring.py -v`
Expected: All 7 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_server_scoring.py
git commit -m "test: add server scoring integration tests with mocked browser"
```

---

## Task 11: Final Integration Verification

- [ ] **Step 1: Run full test suite**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify server module imports cleanly**

Run: `cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -c "from server import NaukriMCPServer, app; print(f'Server OK, {len(app._tool_handlers) if hasattr(app, \"_tool_handlers\") else \"tools registered\"} ')"`

- [ ] **Step 3: Verify scorer works against master resume**

Run:
```bash
cd "/Users/navjeetkajal/Desktop/navjeet projects/Naukri-MCP" && .venv/bin/python -c "
import os
from resume_scorer import ResumeScorer
s = ResumeScorer(os.path.expanduser('~/.naukri-mcp/master_resume.yaml'))
result = s.score('We need a Senior Node.js Developer with experience in Kafka, PostgreSQL, Redis, microservices, and AWS.')
print(f'Score: {result.overall_score}')
print(f'Matched: {result.matched_skills}')
print(f'Missing: {result.missing_skills}')
print(f'Recommendation: {result.recommendation}')
print(f'Gap: {result.gap_analysis}')
"
```
Expected: Score > 0.5 with several matched skills

- [ ] **Step 4: Final commit (if any uncommitted changes)**

```bash
git add -A
git commit -m "feat: complete AI-enhanced job application pipeline implementation"
```

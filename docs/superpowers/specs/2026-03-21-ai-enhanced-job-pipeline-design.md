# AI-Enhanced Job Application Pipeline — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Author:** Navjeet Kajal + Claude Opus 4.6

---

## 1. Problem Statement

The current Naukri-MCP workflow applies jobs with a one-size-fits-all resume. There is no JD analysis, no resume-JD scoring, and no iterative tailoring. This leads to:
- Low ATS pass-through rates (generic resume doesn't match JD keywords)
- Wasted applications on poor-fit jobs
- No way to know which resume version was sent where

## 2. Goals

1. **Score every job** against the master resume before applying (keyword + TF-IDF)
2. **Auto-skip** jobs scoring below 50% match
3. **Iteratively tailor** the resume until it scores >70% ATS match (max 3 iterations)
4. **Enforce truthfulness** — AI selects/reorders from a structured YAML resume, never invents
5. **Track everything** — which resume version went to which company, with what score

## 3. Non-Goals

- No DOCX generation (Naukri accepts PDF)
- No external LLM API calls for scoring (Claude is the MCP host, scoring is local)
- No SpaCy or heavy ML dependencies (scikit-learn only for TF-IDF)
- No changes to authentication, job search, or questionnaire flows
- No proxy rotation or advanced anti-bot measures (out of scope for this iteration)

## 4. Architecture

### 4.1 New Components

```
master_resume.yaml          — Structured resume source-of-truth
resume_scorer.py            — Local keyword + TF-IDF scoring engine
resume_versions table       — SQLite table for version tracking
```

### 4.2 Modified Components

```
resume_tailor.py            — YAML-based input, ATS-optimized PDF output
server.py                   — New tools + modified get_resume_data
models.py                   — New ResumeScore and ResumeVersion models
tracker.py                  — New resume_versions table and methods
```

### 4.3 Unchanged Components

```
naukri.py                   — Browser automation (no changes)
```

### 4.4 Component Diagram

```
Claude (MCP Client) ─── orchestrates the loop
        │
   MCP Server (server.py)
    ├── NaukriClient (naukri.py)       — unchanged
    ├── ResumeScorer (resume_scorer.py) — NEW
    ├── ResumeTailor (resume_tailor.py) — MODIFIED
    ├── JobTracker (tracker.py)        — MODIFIED (new table)
    ├── Models (models.py)             — MODIFIED (new models)
    └── master_resume.yaml             — NEW (user-maintained)
```

## 5. YAML Master Resume Format

File location: `~/.naukri-mcp/master_resume.yaml`

**Error handling:** If the YAML file does not exist, any tool that depends on it (`score_resume_match`, `get_resume_data`) returns a clear error: `"master_resume.yaml not found at {path}. Create it at ~/.naukri-mcp/master_resume.yaml"`. The YAML is validated on load using a Pydantic model (`MasterResume`) — missing required sections (meta, skills, experience) produce specific error messages.

```yaml
meta:
  name: "Navjeet Kajal"
  email: "navjeetkajal.2594@gmail.com"
  phone: "+91-8968118009"
  location: "India"
  github: "github.com/navjeetkajal"
  linkedin: "linkedin.com/in/navjeetkajal"

summary:
  default: "Senior Software Engineer with 4+ years of experience building scalable backend systems, real-time data pipelines, and microservices architectures using Node.js, TypeScript, PostgreSQL, Kafka, and AWS."
  variants:
    backend: "Backend engineer specializing in high-throughput distributed systems, microservices, and real-time data processing with Node.js, Kafka, PostgreSQL, and AWS."
    fullstack: "Full-stack developer with deep backend expertise in Node.js/TypeScript and frontend experience in React.js, building end-to-end web applications."
    devops: "Software engineer with strong infrastructure skills in Docker, AWS (S3, EC2, KMS, SQS, EventBridge), CI/CD, and containerized microservices deployments."

skills:
  - category: "Languages"
    items: ["JavaScript", "TypeScript", "SQL", "HTML/CSS"]
  - category: "Frameworks"
    items: ["NestJS", "Node.js", "Express.js", "React.js", "TailwindCSS"]
  - category: "Libraries"
    items: ["Redux", "Socket.io", "WebRTC", "Zod", "TypeORM"]
  - category: "Infrastructure & Databases"
    items: ["Docker", "AWS (S3, EC2, KMS, SQS, EventBridge)", "Firebase", "Kafka", "Redis", "RabbitMQ", "BullMQ", "PostgreSQL", "MongoDB", "MySQL"]
  - category: "Other"
    items: ["Amazon Ads API", "Amazon SP-API", "Microservices Architecture", "REST API Development", "API Integration", "Message Queues", "Real-time Data Processing"]

experience:
  - company: "Primathon"
    role: "SDE II"
    dates: "Nov 2024 - Present"
    location: "Gurgaon (Hybrid)"
    achievements:
      - id: "pri-xneeti-arch"
        text: "Designed and implemented the backend architecture for Xneeti, an Amazon Ads & SP-API integrated analytics and brand management platform, enabling sellers to track sales, ad spend, ROAS, TACoS, and campaign/keyword performance."
        tags: ["architecture", "backend", "amazon-api", "analytics", "nestjs", "system-design"]
      - id: "pri-onboarding"
        text: "Built onboarding and refresh-token services using LWA, BullMQ, and Redis to authenticate sellers, import historical (90-day) data, and ensure uninterrupted API access across all modules."
        tags: ["authentication", "bullmq", "redis", "api-integration", "backend"]
      - id: "pri-scheduler"
        text: "Engineered a modular scheduler microservice with RabbitMQ for large-scale data synchronization of ads, orders, inventory, and catalog, including batch polling, S3 storage, and PostgreSQL ingestion pipelines."
        tags: ["microservices", "rabbitmq", "scheduler", "postgresql", "aws-s3", "data-pipeline", "backend"]
      - id: "pri-realtime-sync"
        text: "Developed real-time sync capabilities by integrating Amazon SP-API notifications via AWS SQS/EventBridge to capture order status changes, product updates, and inventory fluctuations."
        tags: ["real-time", "aws-sqs", "aws-eventbridge", "api-integration", "event-driven"]
      - id: "pri-campaign"
        text: "Implemented campaign creation and day-parting automation features, allowing sellers to launch optimized ad campaigns, dynamically adjust bids, and pause/resume campaigns, increasing sales efficiency."
        tags: ["automation", "campaign-management", "backend", "feature-development"]
      - id: "pri-api-research"
        text: "Led API research, system design, and module development using NestJS, TypeORM, PostgreSQL, Redis, RabbitMQ, AWS (S3, EC2, KMS, SQS, EventBridge), ensuring scalability, reliability, and compliance with Amazon's API limits."
        tags: ["nestjs", "typeorm", "postgresql", "redis", "rabbitmq", "aws", "system-design", "leadership"]
      - id: "pri-dual-backend"
        text: "Architected dual-backend infrastructure separating platform-facing REST API services from a dedicated scheduler microservice, improving scalability, fault isolation, and maintainability."
        tags: ["architecture", "microservices", "scalability", "system-design", "backend"]
      - id: "pri-collab"
        text: "Collaborated with the product team to translate brand management and performance optimization requirements into scalable backend modules, ensuring timely delivery of high-impact features."
        tags: ["collaboration", "product", "leadership", "backend"]

  - company: "HKB Development Pvt. Ltd."
    role: "NodeJs Backend Developer"
    dates: "Aug 2023 - Nov 2024"
    location: "Mumbai"
    achievements:
      - id: "hkb-streaming"
        text: "Developed and optimized a live video streaming feature for master, admin, and end-user applications, achieving sub-500ms latency. Implemented WebRTC for peer-to-peer communication and adaptive bitrate streaming to handle over 1 million daily active users."
        tags: ["webrtc", "streaming", "real-time", "performance", "scalability", "node.js"]
      - id: "hkb-messaging"
        text: "Implemented real-time messaging functionalities using socket.io, including Winner Number, Jackpot, and Winner List updates, facilitating instantaneous communication between clients and Node.js servers."
        tags: ["socket.io", "real-time", "websocket", "node.js", "messaging"]
      - id: "hkb-microservices"
        text: "Administered and scaled 8 backend microservices with load balancing to support 3 frontend applications. Deployed and managed WebSocket servers using Docker to ensure efficient and scalable architecture."
        tags: ["microservices", "docker", "load-balancing", "scalability", "devops", "websocket"]

  - company: "Immanent Solutions Pvt. Ltd."
    role: "Software Developer"
    dates: "Jan 2022 - May 2023"
    location: "Chandigarh"
    achievements:
      - id: "imm-fullstack"
        text: "Developed and launched full-stack web applications, incorporating payment gateways like Moonava and Stripe, and KYC verification with FrankieOne for users. Leveraged Node.js for backend and MongoDB for database, with Redux ensuring state management."
        tags: ["fullstack", "node.js", "mongodb", "redux", "payment-gateway", "react"]
      - id: "imm-performance"
        text: "Enhanced application performance and scalability by integrating Redis for efficient caching and utilizing TypeScript to ensure robust and type-safe code. Deployed solutions on AWS, leveraging services like EC2 and S3 for optimal resource management."
        tags: ["redis", "typescript", "aws", "performance", "caching", "scalability"]
      - id: "imm-microservices"
        text: "Architected and deployed microservices to handle various functionalities such as user authentication, payment processing, and notifications, resulting in improved scalability and maintainability."
        tags: ["microservices", "architecture", "authentication", "backend"]

projects:
  - name: "Real-time-analytics-platform"
    tech: ["Node.js", "Kafka", "Microservices", "MongoDB", "Docker", "AWS"]
    link: true
    achievements:
      - id: "proj-analytics-arch"
        text: "Architected a real-time analytics platform using microservices to process live financial data, handling thousands of data points per second with Kafka and Node.js."
        tags: ["architecture", "real-time", "kafka", "microservices", "node.js", "data-processing"]
      - id: "proj-analytics-ingest"
        text: "Implemented microservices for high throughput data ingestion, transformation, and storage, integrating the Alpha Vantage API for real-time stock updates with minimal latency."
        tags: ["data-pipeline", "api-integration", "microservices", "performance"]
      - id: "proj-analytics-deploy"
        text: "Deployed and managed the platform on AWS using Docker leveraging containerization, auto-scaling, and distributed processing for robust and scalable operations."
        tags: ["aws", "docker", "devops", "scalability", "deployment"]

  - name: "Chat-App"
    tech: ["MERN"]
    link: true
    achievements:
      - id: "proj-chat-realtime"
        text: "Developed a responsive chat application for real-time messaging by utilizing Socket.io for WebSocket communication."
        tags: ["socket.io", "real-time", "websocket", "node.js"]
      - id: "proj-chat-auth"
        text: "Implemented secure user authentication and role-based access control using JWT for token-based authentication and bcrypt for password hashing."
        tags: ["authentication", "jwt", "security", "node.js"]
      - id: "proj-chat-frontend"
        text: "Created an intuitive and interactive front-end for the chat application using React.js, ensuring a seamless user experience with real-time updates and dynamic UI components."
        tags: ["react", "frontend", "ui", "real-time"]

  - name: "Drone-Simulation"
    tech: ["React", "Redux"]
    link: true
    achievements:
      - id: "proj-drone-sim"
        text: "Developed a real-time drone simulation using React, integrating advanced algorithms for drone navigation and control."
        tags: ["react", "simulation", "algorithms", "frontend"]
      - id: "proj-drone-csv"
        text: "Enabled users to upload CSV files containing drone coordinates and timestamps, automatically updating the simulation path."
        tags: ["react", "file-processing", "frontend"]
      - id: "proj-drone-viz"
        text: "Displayed the drone's current position with a custom marker and dynamically rendered its path using polylines for visual clarity."
        tags: ["react", "visualization", "frontend", "maps"]

education:
  - degree: "Bachelor of Technology in Computer Science and Engineering"
    institution: "Lovely Professional University"
    location: "Punjab"
    dates: "Aug 2017 - Aug 2021"
```

## 6. Scoring Engine (`resume_scorer.py`)

### 6.1 Responsibilities

- Load master_resume.yaml and extract all skills + achievement tags
- Extract keywords from JD text (tech skills, tools, frameworks)
- Compute keyword match score: `matched / total_jd_keywords`
- Compute TF-IDF cosine similarity between resume text and JD text
- Return combined score with matched/missing skills breakdown

### 6.2 Interface

```python
class ResumeScorer:
    def __init__(self, yaml_path: str):
        """Load master resume YAML once."""
        self.resume_data = load_yaml(yaml_path)
        self.all_skills = extract_all_skills(self.resume_data)
        self.all_tags = extract_all_tags(self.resume_data)

    def score(self, jd_text: str, tailored_text: str | None = None) -> ResumeScore:
        """
        Score resume against JD.
        If tailored_text provided, score that instead of master resume.
        """
        resume_text = tailored_text or self._build_resume_text()

        # Layer 1: Keyword matching
        jd_keywords = self._extract_jd_keywords(jd_text)
        matched = jd_keywords & self.all_skills
        keyword_score = len(matched) / max(len(jd_keywords), 1)

        # Layer 2: TF-IDF cosine similarity
        tfidf_score = self._tfidf_similarity(resume_text, jd_text)

        # Combined: 60% keyword, 40% TF-IDF
        # Rationale: TF-IDF with only 2 documents is statistically weak (IDF
        # degenerates to near-uniform weights). Keyword matching is more reliable
        # for our use case. Weights are configurable via SCORE_KEYWORD_WEIGHT env var.
        overall = 0.6 * keyword_score + 0.4 * tfidf_score

        missing = list(jd_keywords - matched)
        gap_analysis = self._build_gap_analysis(list(matched), missing)

        return ResumeScore(
            overall_score=overall,
            keyword_score=keyword_score,
            tfidf_score=tfidf_score,
            matched_skills=list(matched),
            missing_skills=missing,
            gap_analysis=gap_analysis,
            recommendation=self._recommend(overall),
        )

    def _build_gap_analysis(self, matched: list[str], missing: list[str]) -> str:
        """Generate human-readable gap analysis string from matched/missing skills."""
        parts = []
        if matched:
            parts.append(f"Matched: {', '.join(matched[:5])}")
        if missing:
            parts.append(f"Missing: {', '.join(missing[:5])}")
        ratio = len(matched) / max(len(matched) + len(missing), 1)
        if ratio >= 0.7:
            parts.insert(0, "Strong match.")
        elif ratio >= 0.5:
            parts.insert(0, "Moderate match.")
        else:
            parts.insert(0, "Weak match.")
        return " ".join(parts)

    def _extract_jd_keywords(self, jd_text: str) -> set[str]:
        """Extract tech skills/tools from JD using dictionary matching.

        Strategy:
        1. Build a tech-terms dictionary from:
           - All skills.items from YAML (flattened)
           - All achievement tags from YAML
           - A curated base dictionary of ~200 common tech terms
             (languages, frameworks, databases, cloud services, tools)
        2. Normalize JD text to lowercase
        3. Match against dictionary using word-boundary regex (\b...\b)
        4. Handle compound terms: "Node.js", "React.js", "AWS S3" matched as units
        5. Handle parenthetical expansions: "AWS (S3, EC2)" extracts "AWS", "S3", "EC2"
        6. Comparison is case-insensitive
        7. Return set of matched terms (in their canonical casing from dictionary)
        """
        ...

    def _tfidf_similarity(self, text_a: str, text_b: str) -> float:
        """TF-IDF vectorization + cosine similarity."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        tfidf = TfidfVectorizer(stop_words='english')
        matrix = tfidf.fit_transform([text_a, text_b])
        return cosine_similarity(matrix[0:1], matrix[1:2])[0][0]

    def _recommend(self, score: float) -> str:
        if score < 0.50:
            return "skip"
        elif score >= 0.70:
            return "apply_directly"
        else:
            return "tailor"
```

### 6.3 Pydantic Models

```python
class ResumeScore(BaseModel):
    overall_score: float
    keyword_score: float
    tfidf_score: float
    matched_skills: list[str]
    missing_skills: list[str]
    gap_analysis: str          # Human-readable gap summary
    recommendation: str        # "skip" | "tailor" | "apply_directly"

class ResumeVersion(BaseModel):
    id: str                    # Format: "{job_id}_v{iteration}"
    job_id: str
    iteration: int
    file_path: str
    score_before: float | None = None
    score_after: float | None = None
    selected_achievements: list[str] = []  # Achievement IDs from YAML
    created_at: datetime

class MasterResume(BaseModel):
    """Pydantic validator for master_resume.yaml schema."""
    meta: dict                 # Required: name, email, phone
    summary: dict              # Required: default, variants
    skills: list[dict]         # Required: at least one category
    experience: list[dict]     # Required: at least one entry
    projects: list[dict] = []
    education: list[dict] = []
    certifications: list[dict] = []
```

### 6.4 Dependencies

- `scikit-learn` — TF-IDF vectorizer + cosine similarity
- `pyyaml` — YAML parsing
- No other ML libraries

## 7. Enhanced PDF Generation (`resume_tailor.py`)

### 7.1 Changes from Current

| Aspect | Current | New |
|--------|---------|-----|
| Input | Raw text string | Tailored text (structured by Claude from YAML) |
| Section detection | None | Uppercase lines / lines ending with `:` |
| Bullet formatting | None | Proper indentation with bullet characters |
| Font | Basic reportlab default | Helvetica (ATS-safe) |
| Heading hierarchy | None | 12pt bold headings, 10pt body |
| Contact placement | In text | In body (never header/footer) |

### 7.2 Interface

**Deprecation:** The existing `extract_text(pdf_path)` method is removed. The YAML master resume replaces the base PDF as the source of truth. The Naukri profile fetch (`browser.get_profile()`) is also dropped from `get_resume_data` since the YAML is now authoritative.

**HTML entity escaping:** All tailored text must be escaped via `xml.sax.saxutils.escape()` before passing to ReportLab `Paragraph` objects, since ReportLab interprets HTML. Characters like `<`, `>`, `&` in achievement text would otherwise break rendering.

```python
class ResumeTailor:
    def load_yaml(self, yaml_path: str) -> dict:
        """Load, validate (via MasterResume model), and return structured resume data."""
        ...

    async def generate_pdf(self, tailored_text: str, job_id: str) -> str:
        """Generate ATS-optimized PDF with section hierarchy.
        - Escapes HTML entities in text before rendering
        - Section-aware: detects headings, bullets, contact info
        - ATS-safe fonts (Helvetica, 10-12pt)
        - Returns file path
        """
        ...
```

## 8. Database Changes (`tracker.py`)

### 8.1 New Table: `resume_versions`

```sql
CREATE TABLE IF NOT EXISTS resume_versions (
    id                    TEXT PRIMARY KEY,  -- Format: "{job_id}_v{iteration}"
    job_id                TEXT NOT NULL,
    iteration             INTEGER NOT NULL,
    file_path             TEXT NOT NULL,
    score_before          REAL,
    score_after           REAL,
    selected_achievements TEXT,  -- JSON array of achievement IDs from YAML
    created_at            DATETIME NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
```

**Migration:** The existing `jobs.resume_used` column continues to store the file path of the final resume used for the application. The `resume_versions` table provides the detailed iteration history. No existing columns are changed.

### 8.2 New Methods

```python
async def save_resume_version(self, version: ResumeVersion) -> None
async def get_resume_versions(self, job_id: str) -> list[ResumeVersion]
async def get_best_resume(self, job_id: str) -> ResumeVersion | None
    # Returns version with highest score_after for this job
async def get_iteration_count(self, job_id: str) -> int
    # SELECT COUNT(*) FROM resume_versions WHERE job_id = ?
    # Used by server to derive current iteration number
async def get_application_stats(self) -> dict
    # Aggregates: total scored, skipped, applied, failed,
    # avg initial/final scores, avg iterations
    # SQL joins jobs + resume_versions tables
```

## 9. New/Modified MCP Tools

### 9.1 `score_resume_match` (NEW)

```
Parameters:
  - job_id: str (required) — must have JD fetched via get_job_details first
  - tailored_text: str (optional) — if provided, scores this instead of master resume

Returns:
  {
    "overall_score": 0.62,
    "keyword_score": 0.55,
    "tfidf_score": 0.68,
    "matched_skills": ["Node.js", "Kafka", "PostgreSQL"],
    "missing_skills": ["Python", "Django"],
    "gap_analysis": "Strong backend match. Missing Python/Django keywords.",
    "recommendation": "tailor"  // "skip" | "tailor" | "apply_directly"
  }
```

### 9.2 `get_resume_data` (MODIFIED)

Current: Returns raw PDF text + Naukri profile + JD.
New: Returns structured YAML data + JD + latest score + gap analysis. The Naukri profile fetch is dropped — YAML is now the source of truth.

**Iteration tracking:** The server derives the current iteration from `tracker.get_iteration_count(job_id)` (database-derived, survives restarts). No iteration parameter needed from Claude.

```
Returns:
  {
    "job_id": "J123",
    "job_title": "Senior Backend Engineer",
    "company": "Acme Corp",
    "job_description": "...full JD...",
    "resume_data": { ...parsed YAML object... },
    "current_score": { ...latest ResumeScore... },
    "iteration": 1,  // derived from DB: count of existing versions + 1
    "instructions": "Select and reorder achievements from resume_data that best match the job_description. Use missing_skills from current_score to guide emphasis. Do NOT invent new achievements. You may adapt summary from variants. Reorder skill categories to front-load most relevant."
  }
```

### 9.3 `generate_resume` (MODIFIED — renamed from `generate_and_upload_resume`)

**Critical change:** Split into two operations. `generate_resume` only generates the PDF locally and saves a version record. Upload happens separately via `upload_and_apply` only after the score threshold is met. This prevents uploading a suboptimal resume to Naukri during the tailoring loop.

```
Parameters:
  - job_id: str (required)
  - tailored_text: str (required)

Returns (success):
  {
    "success": true,
    "resume_path": "/path/to/generated.pdf",
    "iteration": 2,
    "message": "Resume generated locally. Call score_resume_match to verify, then upload_and_apply when ready."
  }

Returns (error):
  {
    "success": false,
    "error": "PDF generation failed: ...",
    "resume_path": null
  }
```

### 9.4 `upload_and_apply` (NEW)

Uploads the best-scoring resume to Naukri profile, then applies. Called only when the tailoring loop is complete. Also used for the "apply_directly" path (score >= 0.70 on first check) — in that case, the master resume is uploaded as-is.

```
Parameters:
  - job_id: str (required)

Behavior:
  1. tracker.get_best_resume(job_id) → best scoring version
     IF no versions exist (direct apply): use master resume PDF
  2. browser.upload_resume(best.file_path) → upload to Naukri
  3. browser.apply_to_job(job_id) → submit application
  4. tracker.mark_applied(job_id, best.file_path)

Returns: Same as current apply_job response (ApplicationResult or questionnaire dict)
```

**Note:** `upload_and_apply` replaces `apply_job` as the primary application tool for all scored jobs. The existing `apply_job` tool is kept only for backward compatibility (manual/unscored applications).

### 9.5 `get_application_stats` (NEW)

```
Parameters: none

Returns:
  {
    "session_stats": {
      "total_scored": 15,
      "skipped_low_score": 4,
      "applied": 8,
      "failed": 1,
      "pending": 2,
      "avg_initial_score": 0.58,
      "avg_final_score": 0.74,
      "avg_iterations": 1.8
    }
  }
```

## 10. Claude Orchestration Flow

For each approved job, Claude executes:

```
1. get_job_details(job_id) → full JD

2. score_resume_match(job_id) → initial score
   IF recommendation == "skip" (score < 0.50):
     → Log: "Skipped [company] [title] — score: X, missing: [skills]"
     → Next job
   IF recommendation == "apply_directly" (score >= 0.70):
     → Skip tailoring, go directly to step 7

3. get_resume_data(job_id) → YAML data + JD + gaps + iteration (from DB)

4. Claude tailors resume:
   - Picks most relevant summary variant
   - Selects achievements by tag relevance to JD
   - Reorders skill categories (most relevant first)
   - Ensures missing_skills keywords appear where truthful
   - Formats as structured text with proper sections

5. generate_resume(job_id, tailored_text)
   → PDF generated LOCALLY, version saved to DB (NOT uploaded yet)

6. score_resume_match(job_id, tailored_text) → new score
   IF score >= 0.70 → proceed to step 7
   IF score < 0.70 AND iteration < 3:
     → get_resume_data(job_id) → iteration auto-incremented from DB
     → Back to step 4 with updated gap feedback
   IF score < 0.70 AND iteration == 3:
     → Proceed to step 7 (best version will be selected automatically)

7. upload_and_apply(job_id)
   → Picks best-scoring resume version from DB
   → Uploads ONLY the best version to Naukri profile
   → Submits application
   → IF needs_questionnaire → Claude answers → submit_questionnaire
   → Done, next job
```

**Key invariant:** No resume is uploaded to Naukri until the tailoring loop is complete. Only the best-scoring version is ever uploaded. This prevents polluting the Naukri profile with intermediate versions.

## 11. Configuration

### 11.1 New .env Variables

```env
# Existing
NAUKRI_PHONE=8968118009
BASE_RESUME_PATH=/Users/navjeetkajal/Downloads/Work - Docs/Navjeet Resume 2025.pdf
MAX_APPLICATIONS_PER_SESSION=50
RESUME_OUTPUT_DIR=~/.naukri-mcp/resumes

# New
MASTER_RESUME_YAML=~/.naukri-mcp/master_resume.yaml
MIN_MATCH_SCORE=0.50        # Skip jobs below this score
TARGET_ATS_SCORE=0.70       # Target score after tailoring
MAX_TAILOR_ITERATIONS=3     # Max tailoring attempts per job
SCORE_KEYWORD_WEIGHT=0.6    # Weight for keyword score (TF-IDF gets 1 - this)
```

## 12. Dependencies

### 12.1 New

```
scikit-learn>=1.4.0    # TF-IDF + cosine similarity
pyyaml>=6.0.0          # YAML parsing
```

### 12.2 Removed

```
pdfplumber>=0.10.0     # No longer needed — extract_text removed, YAML replaces PDF as source
```

### 12.3 Unchanged

```
mcp>=1.0.0
httpx>=0.27.0
playwright>=1.40.0
reportlab>=4.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
aiosqlite>=0.20.0
```

## 13. File Changes Summary

| File | Action | What Changes |
|------|--------|-------------|
| `~/.naukri-mcp/master_resume.yaml` | **Create** | Structured resume from user's docx |
| `resume_scorer.py` | **Create** | Keyword + TF-IDF scoring engine |
| `resume_tailor.py` | **Modify** | Remove extract_text, add load_yaml, ATS-optimized PDF with HTML escaping |
| `server.py` | **Modify** | 3 new tools (score_resume_match, get_application_stats, upload_and_apply), 2 modified (get_resume_data, generate_resume renamed) |
| `models.py` | **Modify** | Add ResumeScore, ResumeVersion, MasterResume models |
| `tracker.py` | **Modify** | Add resume_versions table, get_iteration_count, get_best_resume, get_application_stats |
| `requirements.txt` | **Modify** | Add scikit-learn, pyyaml |
| `.env` | **Modify** | Add MASTER_RESUME_YAML, MIN_MATCH_SCORE, TARGET_ATS_SCORE, MAX_TAILOR_ITERATIONS, SCORE_KEYWORD_WEIGHT |
| `tests/fixtures/` | **Create** | sample_resume.yaml, sample_jd.txt, sample_jd_poor_match.txt |

## 14. Testing Strategy

Tests follow existing patterns in `tests/` directory.

**Test fixtures (shared):**
- `tests/fixtures/sample_resume.yaml` — minimal valid YAML resume
- `tests/fixtures/sample_jd.txt` — sample job description text
- `tests/fixtures/sample_jd_poor_match.txt` — JD with no skill overlap

**Unit tests:**
- **test_resume_scorer.py**: Score known JD + resume pairs, verify keyword extraction handles compound terms ("Node.js", "AWS S3"), test threshold recommendations, test gap_analysis generation
- **test_resume_tailor.py**: PDF generation produces valid PDF, sections are detected correctly, HTML entities are escaped, bullet points render properly
- **test_tracker_versions.py**: resume_versions CRUD, get_best_resume returns highest score, get_iteration_count is accurate, get_application_stats aggregates correctly
- **test_models.py**: Add ResumeScore, ResumeVersion, MasterResume validation tests

**Integration tests:**
- **test_server_scoring.py**: Full score → tailor → re-score loop with mocked NaukriClient (mock browser.get_job_details to return fixture JD, mock upload_resume)

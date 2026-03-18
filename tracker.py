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
        async with self._conn.execute(
            "SELECT id FROM jobs WHERE id = ? AND status = 'applied'", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def update_recruiter_status(self, job_id: str, recruiter_status: str):
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
        await self._conn.execute(
            "UPDATE jobs SET skills_gap = ?, match_score = ? WHERE id = ?",
            (json.dumps(gap_skills), match_score, job_id)
        )
        await self._conn.commit()

    def _row_to_job(self, row) -> Job:
        data = dict(row)
        data["skills_required"] = json.loads(data["skills_required"] or "[]")
        data["found_at"] = datetime.fromisoformat(data["found_at"])
        if data.get("applied_at"):
            data["applied_at"] = datetime.fromisoformat(data["applied_at"])
        if data.get("status_checked_at"):
            data["status_checked_at"] = datetime.fromisoformat(data["status_checked_at"])
        raw_gap = data.get("skills_gap")
        data["skills_gap"] = json.loads(raw_gap) if raw_gap else []
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

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

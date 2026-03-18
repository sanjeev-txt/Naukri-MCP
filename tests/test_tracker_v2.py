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

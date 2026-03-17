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

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
    job = Job(
        id="J003", title="Dev", company="Co", location="City",
        skills_required=[], url="http://x.com", found_at=datetime.now(),
        status="applied",
        applied_at=datetime.now(),
        resume_used="/path/to/resume.pdf",
    )
    assert job.applied_at is not None
    assert job.resume_used == "/path/to/resume.pdf"

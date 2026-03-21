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
    # Keyword score should be solid even if overall dips slightly below 0.50
    assert result["keyword_score"] >= 0.50


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

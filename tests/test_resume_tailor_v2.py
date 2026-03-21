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

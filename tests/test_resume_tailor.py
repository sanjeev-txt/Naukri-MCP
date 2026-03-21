import pytest
from pathlib import Path


async def test_generate_pdf_creates_file(tmp_path):
    """generate_pdf saves a PDF file to the output directory."""
    from resume_tailor import ResumeTailor

    tailor = ResumeTailor(output_dir=str(tmp_path))
    pdf_path = await tailor.generate_pdf(
        tailored_text="John Doe\nSenior Python Developer\n\nSkills: Python, FastAPI",
        job_id="J001",
    )
    assert Path(pdf_path).exists()
    assert pdf_path.endswith(".pdf")

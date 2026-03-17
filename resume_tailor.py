import os
from datetime import datetime
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

load_dotenv()


class ResumeTailor:
    """
    Handles PDF generation and resume text extraction only.
    Resume tailoring (AI rewriting) is done by Claude Code itself —
    no separate API key needed.
    """

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(
            output_dir or os.path.expanduser(
                os.getenv("RESUME_OUTPUT_DIR", "~/.naukri-mcp/resumes")
            )
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.chmod(0o700)

    def extract_text(self, pdf_path: str) -> str:
        """Extract plain text from a PDF file."""
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)

    async def generate_pdf(self, tailored_text: str, job_id: str) -> str:
        """Generate an ATS-friendly PDF from plain text. Returns the output path."""
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
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"], fontSize=10, leading=14
        )
        story = []
        for line in tailored_text.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.2 * cm))
            else:
                story.append(Paragraph(line, body_style))

        doc.build(story)
        return output_path

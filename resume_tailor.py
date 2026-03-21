import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import yaml
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from models import MasterResume

load_dotenv()


class ResumeTailor:
    """
    Handles YAML resume loading and ATS-optimized PDF generation.
    Resume tailoring (AI rewriting) is done by Claude Code itself.
    """

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(
            output_dir or os.path.expanduser(
                os.getenv("RESUME_OUTPUT_DIR", "~/.naukri-mcp/resumes")
            )
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.chmod(0o700)

    def load_yaml(self, yaml_path: str) -> dict:
        """Load and validate structured resume data from YAML.
        Raises FileNotFoundError if missing, ValidationError if malformed.
        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(
                f"master_resume.yaml not found at {yaml_path}. "
                f"Create it at ~/.naukri-mcp/master_resume.yaml"
            )
        with open(path) as f:
            data = yaml.safe_load(f)
        MasterResume(**data)  # validate schema
        return data

    async def generate_pdf(self, tailored_text: str, job_id: str) -> str:
        """Generate an ATS-optimized PDF with section hierarchy.

        - Detects headings (UPPERCASE lines or lines ending with ':')
        - Formats bullet points (lines starting with '- ' or '* ')
        - Escapes HTML entities for ReportLab safety
        - Uses ATS-safe Helvetica font, 10-12pt
        - Contact info in body (never header/footer)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
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

        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=12,
            spaceAfter=6,
            spaceBefore=12,
            textColor=black,
        )

        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            spaceAfter=3,
        )

        bullet_style = ParagraphStyle(
            'Bullet',
            parent=body_style,
            bulletIndent=12,
            leftIndent=24,
        )

        story = []
        for line in tailored_text.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 6))
            elif self._is_heading(line):
                story.append(Paragraph(escape(line), heading_style))
            elif line.startswith('- ') or line.startswith('* '):
                bullet_text = escape(line.lstrip('-* ').strip())
                story.append(
                    Paragraph(f'<bullet>&bull;</bullet>{bullet_text}', bullet_style)
                )
            else:
                story.append(Paragraph(escape(line), body_style))

        doc.build(story)
        return output_path

    def _is_heading(self, line: str) -> bool:
        """Detect section headings: all-uppercase or ending with ':'."""
        stripped = line.rstrip(':')
        if stripped.isupper() and len(stripped) > 2:
            return True
        if line.endswith(':') and not line.startswith('-'):
            return True
        return False

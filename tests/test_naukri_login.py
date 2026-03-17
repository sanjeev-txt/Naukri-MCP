import time
import stat
import pytest
from naukri import NaukriBrowser


async def test_delay_is_applied():
    """Verify that _delay() waits at least the configured minimum."""
    browser = NaukriBrowser(email="x@x.com", password="pass", delay_seconds=0.1)
    start = time.monotonic()
    await browser._delay()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.1


def test_session_dir_created_with_correct_permissions():
    """Verify session dir exists at ~/.naukri-mcp/session with mode 700."""
    browser = NaukriBrowser(email="x@x.com", password="pass")
    session_dir = browser.session_dir
    assert session_dir.exists()
    mode = oct(stat.S_IMODE(session_dir.stat().st_mode))
    assert mode == "0o700"


def test_resume_dir_created_with_correct_permissions(tmp_path):
    """Verify resume output dir is created with mode 700."""
    resume_dir = tmp_path / "resumes"
    browser = NaukriBrowser(
        email="x@x.com", password="pass",
        resume_output_dir=str(resume_dir)
    )
    browser._ensure_dirs()
    assert resume_dir.exists()
    mode = oct(stat.S_IMODE(resume_dir.stat().st_mode))
    assert mode == "0o700"

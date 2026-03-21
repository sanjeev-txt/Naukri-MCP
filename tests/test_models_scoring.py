from datetime import datetime
import pytest
from models import ResumeScore, ResumeVersion, MasterResume


def test_resume_score_fields():
    score = ResumeScore(
        overall_score=0.65,
        keyword_score=0.7,
        tfidf_score=0.55,
        matched_skills=["Node.js", "Kafka"],
        missing_skills=["Python"],
        gap_analysis="Moderate match. Matched: Node.js, Kafka. Missing: Python.",
        recommendation="tailor",
    )
    assert score.overall_score == 0.65
    assert score.recommendation == "tailor"
    assert len(score.matched_skills) == 2
    assert "Python" in score.missing_skills


def test_resume_score_recommendation_values():
    for rec in ["skip", "tailor", "apply_directly"]:
        score = ResumeScore(
            overall_score=0.5, keyword_score=0.5, tfidf_score=0.5,
            matched_skills=[], missing_skills=[],
            gap_analysis="test", recommendation=rec,
        )
        assert score.recommendation == rec


def test_resume_version_fields():
    version = ResumeVersion(
        id="J001_v1",
        job_id="J001",
        iteration=1,
        file_path="/tmp/resume.pdf",
        score_before=0.45,
        score_after=0.72,
        selected_achievements=["pri-xneeti-arch", "hkb-streaming"],
        created_at=datetime.now(),
    )
    assert version.id == "J001_v1"
    assert version.iteration == 1
    assert len(version.selected_achievements) == 2


def test_resume_version_optional_scores():
    version = ResumeVersion(
        id="J001_v1", job_id="J001", iteration=1,
        file_path="/tmp/resume.pdf", created_at=datetime.now(),
    )
    assert version.score_before is None
    assert version.score_after is None
    assert version.selected_achievements == []


def test_master_resume_validation():
    data = {
        "meta": {"name": "Test", "email": "test@test.com", "phone": "1234567890"},
        "summary": {"default": "A developer.", "variants": {"backend": "Backend dev."}},
        "skills": [{"category": "Languages", "items": ["Python"]}],
        "experience": [{"company": "Co", "role": "Dev", "dates": "2020-2024", "achievements": []}],
    }
    resume = MasterResume(**data)
    assert resume.meta["name"] == "Test"
    assert len(resume.skills) == 1


def test_master_resume_optional_fields():
    data = {
        "meta": {"name": "Test", "email": "t@t.com", "phone": "123"},
        "summary": {"default": "Dev.", "variants": {}},
        "skills": [{"category": "Lang", "items": ["JS"]}],
        "experience": [{"company": "Co", "role": "Dev", "dates": "2024", "achievements": []}],
    }
    resume = MasterResume(**data)
    assert resume.projects == []
    assert resume.education == []
    assert resume.certifications == []

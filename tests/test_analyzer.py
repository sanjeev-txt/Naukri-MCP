# tests/test_analyzer.py
import pytest
from analyzer import RejectionAnalyzer
from models import Job, CandidateProfile
from datetime import datetime

def make_job(job_id, skills_required, recruiter_status, match_score=None, skills_gap=None):
    return Job(
        id=job_id, title="Dev", company="ACME", location="Delhi",
        url=f"https://naukri.com/{job_id}", found_at=datetime.now(),
        status="applied", skills_required=skills_required,
        recruiter_status=recruiter_status,
        skills_gap=skills_gap or [],
        match_score=match_score,
    )

@pytest.fixture
def profile():
    return CandidateProfile(
        current_ctc=8, expected_ctc=14, notice_period_days=60,
        total_experience_years=4, current_location="Faridabad",
        willing_to_relocate=True,
        skills=["Python", "Django", "FastAPI", "LangChain", "PostgreSQL"],
    )

def test_compute_match_score(profile):
    a = RejectionAnalyzer(profile)
    score = a.compute_match_score(["Python", "FastAPI", "Kubernetes"], profile.skills)
    assert score == pytest.approx(66, abs=5)  # 2/3 matched

def test_compute_gap(profile):
    a = RejectionAnalyzer(profile)
    gap = a.compute_gap(["Python", "FastAPI", "Kubernetes", "Go"], profile.skills)
    assert "Kubernetes" in gap
    assert "Go" in gap
    assert "Python" not in gap

def test_aggregate_missing_skills(profile):
    a = RejectionAnalyzer(profile)
    jobs = [
        make_job("j1", ["Python", "Kubernetes", "Go"], "rejected", skills_gap=["Kubernetes", "Go"]),
        make_job("j2", ["Python", "Kubernetes", "Kafka"], "viewed", skills_gap=["Kubernetes", "Kafka"]),
        make_job("j3", ["Python", "Kubernetes", "Redis"], "applied", skills_gap=["Kubernetes", "Redis"]),
    ]
    freq = a.aggregate_missing_skills(jobs)
    assert freq["Kubernetes"] == 3
    assert freq["Go"] == 1

def test_suggest_resume_improvements(profile):
    a = RejectionAnalyzer(profile)
    freq = {"Kubernetes": 5, "Go": 3, "System Design": 2}
    suggestions = a.suggest_resume_improvements(freq, min_count=2)
    assert any("Kubernetes" in s for s in suggestions)
    assert any("Go" in s for s in suggestions)

def test_classify_rejection_reason(profile):
    a = RejectionAnalyzer(profile)
    # never viewed = ATS issue
    assert a.classify_rejection_reason(None) == "ats_filtered"
    # viewed but not shortlisted = content issue
    assert a.classify_rejection_reason("viewed") == "content_gap"
    assert a.classify_rejection_reason("shortlisted") == "shortlisted"

import os
import pytest
from pathlib import Path
from resume_scorer import ResumeScorer
from models import ResumeScore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def scorer():
    return ResumeScorer(str(FIXTURES / "sample_resume.yaml"))


@pytest.fixture
def good_jd():
    return (FIXTURES / "sample_jd.txt").read_text()


@pytest.fixture
def poor_jd():
    return (FIXTURES / "sample_jd_poor_match.txt").read_text()


def test_scorer_loads_yaml(scorer):
    assert scorer.resume_data is not None
    assert scorer.resume_data["meta"]["name"] == "Test User"
    assert len(scorer.all_skills) > 0
    assert len(scorer.all_tags) > 0


def test_scorer_extracts_skills_from_yaml(scorer):
    # Skills should include items from all categories
    assert "Node.js" in scorer.all_skills
    assert "PostgreSQL" in scorer.all_skills
    assert "Docker" in scorer.all_skills


def test_scorer_extracts_tags_from_yaml(scorer):
    # Tags come from achievement tags
    assert "kafka" in scorer.all_tags
    assert "microservices" in scorer.all_tags
    assert "redis" in scorer.all_tags


def test_score_good_match(scorer, good_jd):
    result = scorer.score(good_jd)
    assert isinstance(result, ResumeScore)
    assert result.overall_score >= 0.45  # keyword match is strong, TF-IDF drags down slightly
    assert result.recommendation in ("skip", "tailor", "apply_directly")
    assert len(result.matched_skills) > 0
    assert "Node.js" in result.matched_skills or "node.js" in [s.lower() for s in result.matched_skills]


def test_score_poor_match(scorer, poor_jd):
    result = scorer.score(poor_jd)
    assert isinstance(result, ResumeScore)
    assert result.overall_score < 0.50
    assert result.recommendation == "skip"
    assert len(result.missing_skills) >= len(result.matched_skills)


def test_score_returns_gap_analysis(scorer, good_jd):
    result = scorer.score(good_jd)
    assert isinstance(result.gap_analysis, str)
    assert len(result.gap_analysis) > 0
    # Should mention match quality
    assert any(word in result.gap_analysis.lower() for word in ["match", "matched", "missing"])


def test_score_with_tailored_text(scorer, good_jd):
    tailored = """
    Senior Backend Engineer with 4+ years experience in Node.js, TypeScript, PostgreSQL, Redis, Kafka.
    Built microservices with NestJS and Docker on AWS. Real-time data processing expert.
    """
    result = scorer.score(good_jd, tailored_text=tailored)
    assert isinstance(result, ResumeScore)
    # Tailored text should score at least as well as master
    master_result = scorer.score(good_jd)
    assert result.overall_score >= master_result.overall_score - 0.1  # some tolerance


def test_extract_jd_keywords_handles_compound_terms(scorer):
    jd = "We need experience with Node.js, React.js, and AWS S3."
    keywords = scorer._extract_jd_keywords(jd)
    # Should find compound terms as units
    assert any("node" in k.lower() for k in keywords)


def test_score_keyword_and_tfidf_both_populated(scorer, good_jd):
    result = scorer.score(good_jd)
    assert 0.0 <= result.keyword_score <= 1.0
    assert 0.0 <= result.tfidf_score <= 1.0
    assert 0.0 <= result.overall_score <= 1.0


def test_scorer_missing_yaml_raises_error():
    with pytest.raises(FileNotFoundError):
        ResumeScorer("/nonexistent/path/resume.yaml")

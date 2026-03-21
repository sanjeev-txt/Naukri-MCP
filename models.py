from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class Job(BaseModel):
    id: str
    title: str
    company: str
    location: str
    salary: str | None = None
    skills_required: list[str] = Field(default_factory=list)
    url: str
    status: str = "found"
    found_at: datetime
    # Populated after application lifecycle events
    applied_at: datetime | None = None
    resume_used: str | None = None
    error_message: str | None = None


class JobDetail(Job):
    description: str
    experience_required: str
    posted_at: str
    applicants: int | None = None


class ApplicationResult(BaseModel):
    job_id: str
    success: bool
    resume_used: str | None
    used_tailored_resume: bool
    error: str | None
    applied_at: datetime


class NaukriProfile(BaseModel):
    headline: str
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)


class ResumeScore(BaseModel):
    overall_score: float
    keyword_score: float
    tfidf_score: float
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    gap_analysis: str
    recommendation: str  # "skip" | "tailor" | "apply_directly"


class ResumeVersion(BaseModel):
    id: str  # Format: "{job_id}_v{iteration}"
    job_id: str
    iteration: int
    file_path: str
    score_before: float | None = None
    score_after: float | None = None
    selected_achievements: list[str] = Field(default_factory=list)
    created_at: datetime


class MasterResume(BaseModel):
    """Pydantic validator for master_resume.yaml schema."""
    meta: dict  # Required: name, email, phone
    summary: dict  # Required: default, variants
    skills: list[dict]  # Required: at least one category
    experience: list[dict]  # Required: at least one entry
    projects: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    certifications: list[dict] = Field(default_factory=list)

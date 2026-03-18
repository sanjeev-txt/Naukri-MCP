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


class CandidateProfile(BaseModel):
    current_ctc: float          # e.g. 8.0 (LPA)
    expected_ctc: float         # e.g. 14.0
    notice_period_days: int     # e.g. 60
    total_experience_years: float  # e.g. 4.0
    current_location: str       # e.g. "Faridabad"
    willing_to_relocate: bool   # True
    skills: list[str] = Field(default_factory=list)

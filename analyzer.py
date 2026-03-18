# analyzer.py
from collections import Counter
from models import Job, CandidateProfile


class RejectionAnalyzer:
    def __init__(self, profile: CandidateProfile):
        self.profile = profile
        self._profile_skills_lower = {s.lower() for s in profile.skills}

    def compute_match_score(self, jd_skills: list[str], profile_skills: list[str]) -> int:
        """Return 0-100 score: % of JD skills present in profile."""
        if not jd_skills:
            return 100
        profile_lower = {s.lower() for s in profile_skills}
        matched = sum(1 for s in jd_skills if s.lower() in profile_lower)
        return int(matched / len(jd_skills) * 100)

    def compute_gap(self, jd_skills: list[str], profile_skills: list[str]) -> list[str]:
        """Return skills in JD that are NOT in the profile."""
        profile_lower = {s.lower() for s in profile_skills}
        return [s for s in jd_skills if s.lower() not in profile_lower]

    def classify_rejection_reason(self, recruiter_status: str | None) -> str:
        """
        Classify why a job wasn't shortlisted.
        - None / 'applied' = ATS never surfaced the resume (keyword mismatch)
        - 'viewed' = recruiter saw it but didn't shortlist (content gap)
        - 'shortlisted' = success
        - 'rejected' = explicit rejection
        """
        if recruiter_status in (None, "applied"):
            return "ats_filtered"
        if recruiter_status == "viewed":
            return "content_gap"
        if recruiter_status == "shortlisted":
            return "shortlisted"
        if recruiter_status == "rejected":
            return "content_gap"
        return "unknown"

    def aggregate_missing_skills(self, jobs: list[Job]) -> dict[str, int]:
        """
        Count how often each missing skill appears across rejected/unshortlisted jobs.
        Returns {skill: frequency} sorted descending.
        """
        counter: Counter = Counter()
        for job in jobs:
            for skill in (job.skills_gap or []):
                counter[skill] += 1
        return dict(counter.most_common())

    def suggest_resume_improvements(
        self, freq: dict[str, int], min_count: int = 2
    ) -> list[str]:
        """Generate human-readable resume improvement suggestions."""
        suggestions = []
        for skill, count in freq.items():
            if count >= min_count:
                suggestions.append(
                    f"Add '{skill}' to your resume — missing from {count} job(s) you applied to."
                )
        return suggestions

    def suggest_profile_improvements(self, freq: dict[str, int], min_count: int = 2) -> list[str]:
        """Suggest Naukri profile keyword additions."""
        suggestions = []
        for skill, count in freq.items():
            if count >= min_count and skill.lower() not in self._profile_skills_lower:
                suggestions.append(
                    f"Add '{skill}' to your Naukri profile skills — demanded in {count} target role(s)."
                )
        return suggestions

    def analyze(self, applied_jobs: list[Job]) -> dict:
        """
        Full analysis: categorize jobs, find gaps, return structured insights.
        """
        shortlisted = [j for j in applied_jobs if j.recruiter_status == "shortlisted"]
        viewed_not_shortlisted = [j for j in applied_jobs if j.recruiter_status == "viewed"]
        never_viewed = [j for j in applied_jobs if j.recruiter_status in (None, "applied")]
        rejected = [j for j in applied_jobs if j.recruiter_status == "rejected"]

        # All non-successful jobs for gap analysis
        unsuccessful = viewed_not_shortlisted + never_viewed + rejected
        freq = self.aggregate_missing_skills(unsuccessful)

        avg_score = (
            sum(j.match_score for j in applied_jobs if j.match_score is not None) /
            max(len([j for j in applied_jobs if j.match_score is not None]), 1)
        )

        return {
            "total_applied": len(applied_jobs),
            "shortlisted": len(shortlisted),
            "viewed_not_shortlisted": len(viewed_not_shortlisted),
            "never_viewed": len(never_viewed),
            "rejected": len(rejected),
            "average_match_score": round(avg_score, 1),
            "common_missing_skills": freq,
            "ats_issue": len(never_viewed) > len(applied_jobs) * 0.5,
            "content_issue": len(viewed_not_shortlisted) > len(shortlisted),
            "resume_suggestions": self.suggest_resume_improvements(freq),
            "profile_suggestions": self.suggest_profile_improvements(freq),
        }

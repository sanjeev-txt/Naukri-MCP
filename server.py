import asyncio
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from models import Job, ApplicationResult, CandidateProfile
from naukri import NaukriClient as NaukriBrowser, NaukriError, CaptchaError, LoginError, OTPRequiredError
from resume_tailor import ResumeTailor
from tracker import JobTracker

load_dotenv()

app = Server("naukri-mcp")


class NaukriMCPServer:
    def __init__(self):
        self.tracker = JobTracker()
        self.browser = NaukriBrowser(
            max_applications=int(os.getenv("MAX_APPLICATIONS_PER_SESSION", "50")),
        )
        self.tailor = ResumeTailor()
        self.base_resume_path = os.path.expanduser(os.getenv("BASE_RESUME_PATH", "./resume_base.pdf"))
        self._started = False
        self.candidate_profile = CandidateProfile(
            current_ctc=float(os.getenv("CANDIDATE_CURRENT_CTC", "0")),
            expected_ctc=float(os.getenv("CANDIDATE_EXPECTED_CTC", "0")),
            notice_period_days=int(os.getenv("CANDIDATE_NOTICE_DAYS", "60")),
            total_experience_years=float(os.getenv("CANDIDATE_EXPERIENCE_YEARS", "0")),
            current_location=os.getenv("CANDIDATE_LOCATION", ""),
            willing_to_relocate=os.getenv("CANDIDATE_WILLING_TO_RELOCATE", "true").lower() == "true",
            skills=[s.strip() for s in os.getenv("CANDIDATE_SKILLS", "").split(",") if s.strip()],
        )
        from analyzer import RejectionAnalyzer
        self.analyzer = RejectionAnalyzer(self.candidate_profile)

    async def start(self):
        await self.tracker.init()
        await self.browser.start()
        self._started = True

    async def stop(self):
        await self.browser.stop()
        await self.tracker.close()

    async def _debug_login(self) -> dict:
        """Test connectivity and session status."""
        try:
            logged_in = await self.browser._is_logged_in()
            return {
                "logged_in": logged_in,
                "otp_pending": self.browser._otp_pending,
                "session_file": str(self.browser._session_file()),
                "message": "Logged in and session active." if logged_in else "Not logged in — call a tool to trigger OTP login.",
            }
        except Exception as e:
            return {"error": str(e)}

    async def _submit_otp(self, otp: str) -> dict:
        try:
            await self.browser.submit_otp(otp)
            return {"success": True, "message": "OTP verified. You are now logged in."}
        except LoginError as e:
            return {"success": False, "error": str(e)}

    async def _search_jobs(
        self, title: str, location: str, experience: str,
        skills: list[str], max_results: int
    ) -> list[dict]:
        jobs = await self.browser.search_jobs(title, location, experience, skills, max_results)
        for job in jobs:
            # Compute match score and gap vs candidate profile
            if job.skills_required and self.candidate_profile.skills:
                job.match_score = self.analyzer.compute_match_score(
                    job.skills_required, self.candidate_profile.skills
                )
                gap = self.analyzer.compute_gap(job.skills_required, self.candidate_profile.skills)
            else:
                job.match_score = None
                gap = []
            await self.tracker.save_job(job)
            if gap:
                await self.tracker.save_skills_gap(job.id, gap, job.match_score or 0)
        # Sort by match score descending
        jobs.sort(key=lambda j: j.match_score or 0, reverse=True)
        return [j.model_dump(mode="json") for j in jobs]

    async def _get_job_details(self, job_id: str) -> dict:
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found in tracker"}
        detail = await self.browser.get_job_details(job_id, job.url)
        if not detail:
            return {"error": f"Could not fetch details for job {job_id}"}
        return detail.model_dump(mode="json")

    async def _list_pending_jobs(self) -> list[dict]:
        jobs = await self.tracker.list_jobs(status="found")
        return [j.model_dump(mode="json") for j in jobs]

    async def _approve_jobs(self, job_ids: list[str]) -> list[dict]:
        updated = []
        for job_id in job_ids:
            job = await self.tracker.get_job(job_id)
            if job:
                await self.tracker.update_status(job_id, "approved")
                job.status = "approved"
                updated.append(job.model_dump(mode="json"))
        return updated

    async def _get_resume_data(self, job_id: str) -> dict:
        """
        Returns master resume text + Naukri profile + job description so that
        Claude Code can tailor the resume natively (no separate API key needed).
        After tailoring, call generate_and_upload_resume with the result.
        """
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}

        master_text = self.tailor.extract_text(self.base_resume_path) if os.path.exists(self.base_resume_path) else ""
        profile = await self.browser.get_profile()
        detail = await self.browser.get_job_details(job_id, job.url)

        return {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "job_description": detail.description if detail else job.title,
            "master_resume_text": master_text,
            "naukri_profile": {
                "headline": profile.headline,
                "skills": profile.skills,
                "experience": profile.experience,
                "education": profile.education,
            },
            "instructions": (
                "Please tailor the master_resume_text for this job. "
                "Keep all facts truthful. Use ATS-friendly plain text with sections: "
                "Summary, Skills, Experience, Education. "
                "Then call generate_and_upload_resume with the tailored text."
            ),
        }

    async def _generate_and_upload_resume(self, job_id: str, tailored_text: str) -> dict:
        """Generate a PDF from Claude's tailored text and upload it to Naukri profile."""
        try:
            resume_path = await self.tailor.generate_pdf(tailored_text, job_id)
            uploaded = await self.browser.upload_resume(resume_path)
            if not uploaded:
                return {
                    "success": False,
                    "error": "Resume upload to Naukri failed. You can still apply with your existing profile resume.",
                    "resume_path": resume_path,
                }
            return {"success": True, "resume_path": resume_path, "message": "Resume uploaded to Naukri profile."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _auto_answer_question(self, question: dict) -> str | None:
        """
        Auto-answer a recruiter screening question from candidate profile.
        Returns answer string, or None if ambiguous/unknown.
        """
        p = self.candidate_profile
        q_text = (question.get("question") or "").lower()
        q_type = question.get("type", "")
        options = question.get("options") or []

        # Helper: find radio option key by label match
        def radio_key(label: str) -> str | None:
            label_lower = label.lower()
            for opt in options:
                if label_lower in (opt.get("option") or "").lower():
                    return str(opt.get("optionId") or opt.get("id") or "")
            return None

        # CTC questions
        if any(k in q_text for k in ["current ctc", "current salary", "ctc in lacs", "ctc per annum"]):
            if q_type in ("Text Box", "text"):
                return str(int(p.current_ctc)) if p.current_ctc == int(p.current_ctc) else str(p.current_ctc)

        if any(k in q_text for k in ["expected ctc", "expected salary", "salary expectation"]):
            if q_type in ("Text Box", "text"):
                return str(int(p.expected_ctc)) if p.expected_ctc == int(p.expected_ctc) else str(p.expected_ctc)

        # Notice period
        if any(k in q_text for k in ["notice period", "notice in days", "joining time"]):
            if q_type in ("Text Box", "text"):
                return str(p.notice_period_days)
            # Radio: look for matching option
            for opt in options:
                opt_text = (opt.get("option") or "").lower()
                if str(p.notice_period_days) in opt_text or "2 month" in opt_text and p.notice_period_days <= 60:
                    return str(opt.get("optionId") or "")

        # Experience questions
        if any(k in q_text for k in ["years of experience", "experience do you have", "total experience", "how many years"]):
            if q_type in ("Text Box", "text"):
                exp = p.total_experience_years
                return str(int(exp)) if exp == int(exp) else str(exp)
            # Radio: find matching range
            for opt in options:
                opt_text = (opt.get("option") or "").lower()
                if str(int(p.total_experience_years)) in opt_text:
                    return str(opt.get("optionId") or "")

        # Location / relocation
        if any(k in q_text for k in ["relocat", "willing to move", "currently residing", "work from office", "onsite"]):
            if q_type == "Radio Button":
                if p.willing_to_relocate:
                    return radio_key("yes") or radio_key("comfortable") or None
                else:
                    return radio_key("no") or None
            if q_type in ("Text Box", "text"):
                return p.current_location

        # Current location / city
        if any(k in q_text for k in ["current location", "current city", "where are you based"]):
            if q_type in ("Text Box", "text"):
                return p.current_location

        return None  # Cannot auto-answer

    async def _apply_job(self, job_id: str, dry_run: bool) -> dict:
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"success": False, "error": f"Job {job_id} not found"}

        if job.status != "approved":
            return {
                "success": False,
                "error": "Job must be approved before applying. Use approve_job first.",
            }

        if await self.tracker.is_duplicate(job_id):
            return {"success": False, "error": f"Already applied to job {job_id}"}

        # Compute and store skills gap AFTER guards, BEFORE applying
        if job.skills_required:
            gap = self.analyzer.compute_gap(job.skills_required, self.candidate_profile.skills)
            score = self.analyzer.compute_match_score(job.skills_required, self.candidate_profile.skills)
            await self.tracker.save_skills_gap(job.id, gap, score)

        try:
            result = await self.browser.apply_to_job(job.url, dry_run=dry_run)
        except CaptchaError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}
        except NaukriError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}

        # Handle apply-on-company-site result
        if isinstance(result, dict) and result.get("apply_on_company_site"):
            await self.tracker.update_status(job_id, "applied_externally")
            return {
                "success": True,
                "apply_on_company_site": True,
                "external_url": result["external_url"],
                "message": result["message"],
            }

        # Questionnaire required — auto-answer from candidate profile first
        if isinstance(result, dict) and result.get("needs_questionnaire"):
            questions = result.get("questions", [])
            auto_answers = {}
            unanswered = []

            for q in questions:
                q_id = str(q.get("questionId") or q.get("id") or "")
                ans = self._auto_answer_question(q)
                if ans is not None:
                    auto_answers[q_id] = ans
                else:
                    unanswered.append(q)

            if not unanswered:
                # Fully auto-answered — submit immediately
                return await self._submit_questionnaire(job_id, auto_answers)
            else:
                # Return partial answers + questions Claude/user must answer
                result["auto_answered"] = auto_answers
                result["unanswered_questions"] = unanswered
                result["message"] = (
                    f"Auto-answered {len(auto_answers)} question(s). "
                    f"{len(unanswered)} question(s) need your input. "
                    "Call submit_questionnaire with job_id and merged answers dict."
                )
                return result

        if not dry_run and result:
            resume_used = job.__dict__.get("resume_used")
            await self.tracker.mark_applied(job_id, resume_used)

        return ApplicationResult(
            job_id=job_id,
            success=bool(result),
            resume_used=None,
            used_tailored_resume=False,
            error=None if result else "Application button not found",
            applied_at=datetime.now(),
        ).model_dump(mode="json")

    async def _submit_questionnaire(self, job_id: str, answers: dict) -> dict:
        job = await self.tracker.get_job(job_id)
        if not job:
            return {"success": False, "error": f"Job {job_id} not found"}
        try:
            await self.browser.submit_questionnaire(job_id, answers, job.url)
            await self.tracker.mark_applied(job_id, None)
            return ApplicationResult(
                job_id=job_id,
                success=True,
                resume_used=None,
                used_tailored_resume=False,
                error=None,
                applied_at=datetime.now(),
            ).model_dump(mode="json")
        except NaukriError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}

    async def _bulk_apply(self, job_ids: list[str] | None = None) -> dict:
        """
        Apply to all approved jobs (or a specific list).
        Auto-answers questionnaires from candidate profile.
        Returns a summary report.
        """
        if job_ids:
            jobs = [await self.tracker.get_job(jid) for jid in job_ids]
            jobs = [j for j in jobs if j and j.status == "approved"]
        else:
            jobs = await self.tracker.list_jobs(status="approved")

        if not jobs:
            return {"message": "No approved jobs to apply to. Use approve_job first.", "results": []}

        results = []
        for job in jobs:
            try:
                outcome = await self._apply_job(job.id, dry_run=False)
                results.append({
                    "job_id": job.id,
                    "company": job.company,
                    "title": job.title,
                    "outcome": "applied" if outcome.get("success") else "failed",
                    "detail": outcome,
                })
            except Exception as e:
                results.append({
                    "job_id": job.id,
                    "company": job.company,
                    "title": job.title,
                    "outcome": "error",
                    "detail": str(e),
                })

        applied = [r for r in results if r["outcome"] == "applied"]
        # Questionnaire-required: _apply_job returns needs_questionnaire=True — not a failure
        questionnaire_needed = [
            r for r in results
            if isinstance(r.get("detail"), dict) and r["detail"].get("needs_questionnaire")
        ]
        # Company-site redirects
        external = [
            r for r in results
            if isinstance(r.get("detail"), dict) and r["detail"].get("apply_on_company_site")
        ]
        failed = [
            r for r in results
            if r["outcome"] in ("failed", "error")
            and r not in questionnaire_needed
            and r not in external
        ]

        return {
            "total": len(results),
            "applied": len(applied),
            "failed": len(failed),
            "apply_on_company_site": len(external),
            "needs_manual_questionnaire": len(questionnaire_needed),
            "results": results,
            "summary": (
                f"{len(applied)}/{len(results)} applications submitted. "
                f"{len(external)} require manual action on company site. "
                f"{len(questionnaire_needed)} have unresolved questionnaire questions. "
                f"{len(failed)} failed."
            ),
        }

    async def _get_applied_jobs(
        self, status: str | None, since_date: str | None, limit: int
    ) -> list[dict]:
        jobs = await self.tracker.list_jobs(status=status, since_date=since_date, limit=limit)
        return [j.model_dump(mode="json") for j in jobs]

    async def _sync_application_statuses(self) -> dict:
        """Poll Naukri for recruiter status on all applied jobs and update tracker."""
        applied_jobs = await self.tracker.get_applied_jobs_for_sync()
        if not applied_jobs:
            return {"message": "No applied jobs to sync.", "updated": []}

        job_ids = [j.id for j in applied_jobs]
        statuses = await self.browser.fetch_application_statuses(job_ids)

        updated = []
        for job in applied_jobs:
            new_status = statuses.get(job.id)
            if new_status and new_status != job.recruiter_status:
                await self.tracker.update_recruiter_status(job.id, new_status)
                updated.append({
                    "job_id": job.id,
                    "company": job.company,
                    "title": job.title,
                    "old_status": job.recruiter_status or "unknown",
                    "new_status": new_status,
                })

        return {
            "total_checked": len(applied_jobs),
            "updated": updated,
            "message": f"Synced {len(applied_jobs)} applications. {len(updated)} status change(s) found.",
        }

    async def _analyze_rejections(self, since_days: int = 30) -> dict:
        """Analyze all applied jobs to surface rejection patterns."""
        from datetime import timedelta
        since_date = (datetime.now() - timedelta(days=since_days)).isoformat()
        applied_jobs = await self.tracker.list_jobs(status="applied", since_date=since_date)
        if not applied_jobs:
            return {"message": f"No applied jobs found in the last {since_days} days."}
        return self.analyzer.analyze(applied_jobs)

    async def _suggest_improvements(self) -> dict:
        """Aggregate all time rejection data and return resume + profile improvements."""
        applied_jobs = await self.tracker.list_jobs(status="applied")
        if not applied_jobs:
            return {"message": "No applied jobs in tracker yet. Apply to some jobs first."}

        analysis = self.analyzer.analyze(applied_jobs)

        strategy = []
        if analysis["ats_issue"]:
            strategy.append(
                f"{analysis['never_viewed']} of your applications were never viewed. "
                "This is an ATS keyword issue — add missing skills to your resume headline and skills section."
            )
        if analysis["content_issue"]:
            strategy.append(
                f"{analysis['viewed_not_shortlisted']} applications were viewed but not shortlisted. "
                "Recruiters are reading your resume but not finding enough match — strengthen project descriptions."
            )
        if analysis["shortlisted"] > 0:
            strategy.append(
                f"You were shortlisted {analysis['shortlisted']} time(s) — "
                "identify what those job descriptions had in common with your profile."
            )

        return {
            "summary": {
                "total_applied": analysis["total_applied"],
                "shortlisted": analysis["shortlisted"],
                "shortlist_rate": f"{round(analysis['shortlisted'] / max(analysis['total_applied'], 1) * 100, 1)}%",
                "average_match_score": analysis["average_match_score"],
            },
            "diagnosis": strategy,
            "top_missing_skills": list(analysis["common_missing_skills"].items())[:10],
            "resume_improvements": analysis["resume_suggestions"],
            "profile_improvements": analysis["profile_suggestions"],
        }


_server_instance: NaukriMCPServer | None = None


def get_server() -> NaukriMCPServer:
    global _server_instance
    if _server_instance is None:
        _server_instance = NaukriMCPServer()
    return _server_instance


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_jobs",
            description="Search Naukri.com for jobs matching title, location, experience, and skills",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "location": {"type": "string"},
                    "experience": {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["title", "location", "experience"],
            },
        ),
        types.Tool(
            name="get_job_details",
            description="Get full description and details of a specific job by ID",
            inputSchema={
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="list_pending_jobs",
            description="List all jobs found but not yet approved or applied to",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="approve_job",
            description="Approve one or more jobs for application. Must be called before apply_job.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["job_ids"],
            },
        ),
        types.Tool(
            name="get_resume_data",
            description="Fetch master resume text + Naukri profile + job description so Claude can tailor the resume. Call this before generate_and_upload_resume.",
            inputSchema={
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="generate_and_upload_resume",
            description="Generate a PDF from Claude's tailored resume text and upload it to Naukri profile.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "tailored_text": {"type": "string", "description": "The tailored resume as plain text"},
                },
                "required": ["job_id", "tailored_text"],
            },
        ),
        types.Tool(
            name="apply_job",
            description="Submit application for an approved job. Call after generate_and_upload_resume (or directly to apply with existing Naukri profile resume).",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="get_applied_jobs",
            description="View history of applied jobs with optional status/date filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "since_date": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        ),
        types.Tool(
            name="submit_questionnaire",
            description=(
                "Submit answers to a job's screening questionnaire. Call this after apply_job "
                "returns needs_questionnaire=true. Answer each question using the candidate profile; "
                "ask the user for anything ambiguous before calling this tool. "
                "answers is a dict of {questionId: answerValue} where answerValue is the option KEY "
                "(e.g. '3') for Radio Button / List Menu questions, or free text for Text Box."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "answers": {
                        "type": "object",
                        "description": "Map of questionId → answer value",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["job_id", "answers"],
            },
        ),
        types.Tool(
            name="sync_application_statuses",
            description=(
                "Poll Naukri for recruiter status on all your applied jobs "
                "(Viewed / Shortlisted / Rejected / Expired). "
                "Run this 3-7 days after applying to see recruiter activity."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="debug_login",
            description="Check Naukri session status and connectivity. Use this when login fails.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="submit_otp",
            description="Submit OTP for Naukri login. Call this when any tool returns an otp_required error.",
            inputSchema={
                "type": "object",
                "properties": {
                    "otp": {"type": "string", "description": "The OTP sent to your registered email or phone"},
                },
                "required": ["otp"],
            },
        ),
        types.Tool(
            name="analyze_rejections",
            description=(
                "Analyze your recent job applications to find rejection patterns. "
                "Shows shortlist rate, which skills are commonly missing, "
                "and whether the issue is ATS filtering or content gaps. "
                "Run sync_application_statuses first for fresh data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "since_days": {"type": "integer", "default": 30,
                                   "description": "Look back this many days (default 30)"},
                },
            },
        ),
        types.Tool(
            name="suggest_improvements",
            description=(
                "Generate specific resume and Naukri profile improvement suggestions "
                "based on skills gaps found across all rejected applications. "
                "Returns ranked list of missing skills and actionable edits."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="bulk_apply",
            description=(
                "Apply to all approved jobs in one command. "
                "Auto-answers common recruiter questions from your candidate profile. "
                "Pass job_ids to apply to specific jobs, or omit to apply to all approved jobs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "job_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific job IDs to apply to (optional — omit for all approved)",
                    },
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    s = get_server()
    if not s._started:
        await s.start()

    try:
        if name == "search_jobs":
            result = await s._search_jobs(
                arguments["title"], arguments["location"],
                arguments.get("experience", ""), arguments.get("skills", []),
                arguments.get("max_results", 20),
            )
        elif name == "get_job_details":
            result = await s._get_job_details(arguments["job_id"])
        elif name == "list_pending_jobs":
            result = await s._list_pending_jobs()
        elif name == "approve_job":
            result = await s._approve_jobs(arguments["job_ids"])
        elif name == "get_resume_data":
            result = await s._get_resume_data(arguments["job_id"])
        elif name == "generate_and_upload_resume":
            result = await s._generate_and_upload_resume(
                arguments["job_id"], arguments["tailored_text"]
            )
        elif name == "apply_job":
            result = await s._apply_job(
                arguments["job_id"],
                arguments.get("dry_run", False),
            )
        elif name == "get_applied_jobs":
            result = await s._get_applied_jobs(
                arguments.get("status"), arguments.get("since_date"),
                arguments.get("limit", 50),
            )
        elif name == "submit_questionnaire":
            result = await s._submit_questionnaire(
                arguments["job_id"], arguments["answers"]
            )
        elif name == "sync_application_statuses":
            result = await s._sync_application_statuses()
        elif name == "debug_login":
            result = await s._debug_login()
        elif name == "submit_otp":
            result = await s._submit_otp(arguments["otp"])
        elif name == "analyze_rejections":
            result = await s._analyze_rejections(arguments.get("since_days", 30))
        elif name == "suggest_improvements":
            result = await s._suggest_improvements()
        elif name == "bulk_apply":
            result = await s._bulk_apply(arguments.get("job_ids"))
        else:
            result = {"error": f"Unknown tool: {name}"}

    except OTPRequiredError as e:
        result = {
            "otp_required": True,
            "message": str(e),
            "action": "Call the submit_otp tool with the OTP sent to your registered email/phone, then retry.",
        }
    except Exception as e:
        # Surface ALL errors — never silently return empty results
        result = {"error": type(e).__name__, "message": str(e)}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def main():
    s = get_server()
    await s.start()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        await s.stop()


if __name__ == "__main__":
    asyncio.run(main())

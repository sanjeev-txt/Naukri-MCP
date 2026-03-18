import asyncio
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from models import Job, ApplicationResult
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
            await self.tracker.save_job(job)
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

        try:
            result = await self.browser.apply_to_job(job.url, dry_run=dry_run)
        except CaptchaError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}
        except NaukriError as e:
            await self.tracker.mark_failed(job_id, str(e))
            return {"success": False, "error": str(e)}

        # Questionnaire required — return questions to caller (Claude) to answer
        if isinstance(result, dict) and result.get("needs_questionnaire"):
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

    async def _get_applied_jobs(
        self, status: str | None, since_date: str | None, limit: int
    ) -> list[dict]:
        jobs = await self.tracker.list_jobs(status=status, since_date=since_date, limit=limit)
        return [j.model_dump(mode="json") for j in jobs]


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
        elif name == "debug_login":
            result = await s._debug_login()
        elif name == "submit_otp":
            result = await s._submit_otp(arguments["otp"])
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

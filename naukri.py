import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from models import Job, JobDetail, NaukriProfile

load_dotenv()

NAUKRI_BASE = "https://www.naukri.com"

# Discovered from app_v445.min.js bundle reverse-engineering
SEND_OTP_URL     = f"{NAUKRI_BASE}/central-login-services/v1/otp"
VERIFY_OTP_URL   = f"{NAUKRI_BASE}/central-login-services/v0/otp-login"
EMAIL_LOGIN_URL  = f"{NAUKRI_BASE}/central-login-services/v0/login"
LOGIN_STATUS_URL = f"{NAUKRI_BASE}/central-login-services/v0/credentials/login-status"
LOGOUT_URL       = f"{NAUKRI_BASE}/loginapi/v1/logout"

SEARCH_URL       = f"{NAUKRI_BASE}/jobapi/v3/search"
JOB_DETAIL_URL   = f"{NAUKRI_BASE}/jobapi/v4/job"
APPLY_URL        = f"{NAUKRI_BASE}/cloudgateway-workflow/workflow-services/apply-workflow/v1/apply"
APPLY_HISTORY_URL= f"{NAUKRI_BASE}/applyapi/webapphistory"

PROFILE_URL      = f"{NAUKRI_BASE}/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self?expand_level=2"
RESUME_UPLOAD_URL= f"{NAUKRI_BASE}/mnjapi/v1/resume"

BASE_HEADERS = {
    "appid": "100",
    "systemid": "jobseeker",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-requested-with": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.naukri.com",
    "Referer": "https://www.naukri.com/nlogin/login",
}


class NaukriError(Exception):
    pass


class CaptchaError(NaukriError):
    pass


class LoginError(NaukriError):
    pass


class OTPRequiredError(NaukriError):
    pass


class NaukriClient:
    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        phone: str | None = None,
        max_applications: int = 50,
    ):
        self.email = email or os.getenv("NAUKRI_EMAIL", "")
        self.password = password or os.getenv("NAUKRI_PASSWORD", "")
        self.phone = phone or os.getenv("NAUKRI_PHONE", "")
        self.use_phone_otp = bool(self.phone and not self.password)
        self.max_applications = max_applications

        self.session_dir = Path.home() / ".naukri-mcp" / "session"
        self.resume_output_dir = Path(
            os.path.expanduser(os.getenv("RESUME_OUTPUT_DIR", "~/.naukri-mcp/resumes"))
        )
        self._ensure_dirs()

        self._client: httpx.AsyncClient | None = None
        self._logged_in = False
        self._otp_pending = False
        self._applications_this_session = 0
        self._session_date = datetime.now().date()
        self._cookies: dict = {}
        self._auth_token: str | None = None

    def _ensure_dirs(self):
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_dir.chmod(0o700)
        self.resume_output_dir.mkdir(parents=True, exist_ok=True)
        self.resume_output_dir.chmod(0o700)

    async def start(self):
        self._client = httpx.AsyncClient(
            headers=BASE_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        self._load_session()

    async def stop(self):
        if self._client:
            await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Session persistence
    # ------------------------------------------------------------------ #

    def _session_file(self) -> Path:
        return self.session_dir / "api_session.json"

    def _load_session(self):
        sf = self._session_file()
        if sf.exists():
            try:
                data = json.loads(sf.read_text())
                self._cookies = data.get("cookies", {})
                self._auth_token = data.get("auth_token")
                if self._cookies or self._auth_token:
                    self._logged_in = True
            except Exception:
                pass

    def _save_session(self):
        sf = self._session_file()
        sf.write_text(json.dumps({
            "cookies": self._cookies,
            "auth_token": self._auth_token,
        }))
        sf.chmod(0o600)

    def _request_headers(self, extra: dict | None = None) -> dict:
        h = {}
        if self._auth_token:
            token = self._auth_token
            h["authorization"] = token if token.startswith("Bearer ") else f"Bearer {token}"
        if extra:
            h.update(extra)
        return h

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    async def _get(self, url: str, params: dict | None = None) -> dict:
        resp = await self._client.get(
            url, params=params,
            headers=self._request_headers(),
            cookies=self._cookies,
        )
        resp.raise_for_status()
        return resp.json()

    async def _post(self, url: str, payload: dict) -> httpx.Response:
        resp = await self._client.post(
            url, json=payload,
            headers=self._request_headers(),
            cookies=self._cookies,
        )
        return resp

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #

    async def _is_logged_in(self) -> bool:
        if not self._cookies and not self._auth_token:
            return False
        try:
            resp = await self._client.get(
                LOGIN_STATUS_URL,
                headers=self._request_headers(),
                cookies=self._cookies,
            )
            data = resp.json()
            return data.get("loggedin", False)
        except Exception:
            return False

    async def login(self):
        if self._logged_in and await self._is_logged_in():
            return
        if self._otp_pending:
            raise OTPRequiredError(
                "OTP verification is pending. Please call the submit_otp tool "
                "with the OTP sent to your phone/email."
            )
        if self.use_phone_otp:
            await self._send_phone_otp()
        else:
            await self._login_email_password()

    async def _send_phone_otp(self):
        resp = await self._client.post(
            SEND_OTP_URL,
            json={
                "username": self.phone,
                "flowId": "login",
                "isLoginByEmail": False,
                "isLoginByMobile": True,
            },
            headers=self._request_headers(),
        )
        if resp.status_code != 200:
            data = resp.json()
            msg = data.get("message") or str(data)
            raise LoginError(f"OTP send failed: {msg}")
        # Persist the session cookie from this request
        self._cookies.update(dict(resp.cookies))
        self._otp_pending = True
        raise OTPRequiredError(
            f"OTP sent to {self.phone}. Please call the submit_otp tool with the OTP."
        )

    async def _login_email_password(self):
        resp = await self._client.post(
            EMAIL_LOGIN_URL,
            json={"username": self.email, "password": self.password},
            headers=self._request_headers(),
        )
        data = resp.json()
        if resp.status_code == 200 and (data.get("userId") or data.get("authToken")):
            self._auth_token = data.get("authToken") or data.get("jwtToken")
            self._cookies.update(dict(resp.cookies))
            self._logged_in = True
            self._save_session()
        elif data.get("otpRequired"):
            self._otp_pending = True
            raise OTPRequiredError(
                "Naukri requires OTP. Please call submit_otp with the OTP sent to your email/phone."
            )
        else:
            msg = data.get("message") or str(data)
            raise LoginError(f"Login failed: {msg}")

    async def submit_otp(self, otp: str):
        """Complete login by submitting the OTP received on phone."""
        username = self.phone if self.use_phone_otp else self.email
        resp = await self._client.post(
            VERIFY_OTP_URL,
            json={"username": username, "token": otp, "flowId": "login"},
            headers=self._request_headers(),
            cookies=self._cookies,
        )
        data = resp.json()

        # Success: response contains cookies list + userInfo
        user_info = data.get("userInfo", {})
        user_state = data.get("userStateInfo", {})
        if resp.status_code == 200 and (
            user_info.get("userId") or user_state.get("validState")
        ):
            # Extract cookies returned in the response body
            for ck in data.get("cookies", []):
                self._cookies[ck["name"]] = ck["value"]
            # Also pick up any HTTP-level cookies
            self._cookies.update(dict(resp.cookies))
            # Use the access token (JWT) as auth token
            self._auth_token = self._cookies.get("nauk_at")
            self._otp_pending = False
            self._logged_in = True
            self._save_session()
        else:
            msg = data.get("message") or str(data)
            raise LoginError(f"OTP verification failed: {msg}")

    # ------------------------------------------------------------------ #
    # Job search — uses Playwright to bypass Naukri's client-side nkparam
    # (nkparam is a single-use HMAC token generated by Naukri's JS bundle)
    # ------------------------------------------------------------------ #

    async def search_jobs(
        self,
        title: str,
        location: str,
        experience: str,
        skills: list[str],
        max_results: int = 20,
    ) -> list[Job]:
        await self.login()
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise NaukriError(
                "playwright is required for job search. "
                "Install with: pip install playwright && playwright install chromium"
            )

        # Build Naukri SEO-style search URL so the page triggers the search API
        kw_slug = title.lower().replace(" ", "-")
        loc_slug = location.lower().replace(" ", "-")
        search_page_url = (
            f"{NAUKRI_BASE}/{kw_slug}-jobs-in-{loc_slug}"
            f"?experience={experience}"
        )
        if skills:
            search_page_url += f"&k={title}&l={location}"

        captured_jobs: list[dict] = []
        done = asyncio.Event()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            ctx = await browser.new_context()
            await ctx.add_cookies([
                {"name": k, "value": v, "domain": ".naukri.com", "path": "/"}
                for k, v in self._cookies.items()
            ])
            page = await ctx.new_page()

            async def on_response(response):
                if "jobapi/v3/search" in response.url and response.status == 200:
                    try:
                        data = await response.json()
                        captured_jobs.extend(data.get("jobDetails") or [])
                    except Exception:
                        pass
                    done.set()

            page.on("response", on_response)
            try:
                await page.goto(search_page_url, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass

            try:
                await asyncio.wait_for(done.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            await browser.close()

        if not captured_jobs:
            raise NaukriError(
                f"Job search returned no results. "
                f"The session may have expired — try debug_login then re-login."
            )

        jobs = []
        for item in captured_jobs[:max_results]:
            job = self._parse_job(item)
            if job:
                jobs.append(job)
        return jobs

    def _parse_job(self, item: dict) -> Job | None:
        try:
            job_id = str(item.get("jobId") or item.get("id") or "")
            title = item.get("title") or item.get("jobTitle") or ""
            company = item.get("companyName") or item.get("company") or ""
            if isinstance(company, dict):
                company = company.get("label") or company.get("name") or ""

            # placeholders — list of {type, label} dicts (from jobapi/v3/search)
            placeholders = item.get("placeholders") or []
            if isinstance(placeholders, list):
                loc_str = ", ".join(
                    p.get("label", "") for p in placeholders if p.get("type") == "location"
                )
                salary = next(
                    (p.get("label") for p in placeholders if p.get("type") == "salary"), None
                )
            else:
                loc_str = ""
                salary = None

            # tagsAndSkills — list of {label} dicts OR comma-separated string
            raw_skills = item.get("tagsAndSkills") or []
            if isinstance(raw_skills, str):
                skills = [s.strip() for s in raw_skills.split(",") if s.strip()]
            else:
                skills = [t.get("label", "") for t in raw_skills]

            url = item.get("jdURL") or item.get("staticUrl") or f"{NAUKRI_BASE}/job-listings-{job_id}"
            if url and not url.startswith("http"):
                url = NAUKRI_BASE + url
            return Job(
                id=job_id,
                title=title,
                company=company,
                location=loc_str,
                salary=salary,
                skills_required=skills,
                url=url,
                found_at=datetime.now(),
            )
        except Exception:
            return None

    async def get_job_details(self, job_id: str, url: str) -> JobDetail | None:
        """Fetch full job details by navigating to the job page and intercepting the API response."""
        await self.login()
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise NaukriError("playwright is required for job details")

        captured: list[dict] = []
        done = asyncio.Event()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            ctx = await browser.new_context()
            await ctx.add_cookies([
                {"name": k, "value": v, "domain": ".naukri.com", "path": "/"}
                for k, v in self._cookies.items()
            ])
            page = await ctx.new_page()

            async def on_response(response):
                if f"jobapi/v4/job/{job_id}" in response.url and response.status == 200:
                    try:
                        data = await response.json()
                        captured.append(data)
                    except Exception:
                        pass
                    done.set()

            page.on("response", on_response)
            job_url = url if url.startswith("http") else f"{NAUKRI_BASE}{url}"
            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass
            try:
                await asyncio.wait_for(done.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            await browser.close()

        if not captured:
            return None

        data = captured[0]
        jd = data.get("jobDetails") or data
        try:
            title = jd.get("title") or jd.get("jobTitle") or ""
            # companyName is nested in companyDetail in the v4 response
            company_detail = jd.get("companyDetail") or {}
            company = (
                jd.get("companyName")
                or company_detail.get("name")
                or company_detail.get("label")
                or ""
            )
            if isinstance(company, dict):
                company = company.get("label") or company.get("name") or ""

            # Location from placeholders or wfhLabel
            placeholders = jd.get("placeholders") or []
            if isinstance(placeholders, list) and placeholders:
                location = ", ".join(
                    p.get("label", "") for p in placeholders if p.get("type") == "location"
                )
                salary = next(
                    (p.get("label") for p in placeholders if p.get("type") == "salary"), None
                )
            else:
                location = jd.get("wfhLabel") or ""
                salary = None

            description = jd.get("description") or jd.get("jobDescription") or jd.get("shortDescription") or ""
            experience = jd.get("experienceText") or ""
            if not experience:
                min_exp = jd.get("minimumExperience") or 0
                max_exp = jd.get("maximumExperience") or 0
                if min_exp or max_exp:
                    experience = f"{min_exp}-{max_exp} years"
            posted_at = jd.get("createdDate") or jd.get("postedOn") or ""
            skills_raw = jd.get("tagsAndSkills") or []
            if isinstance(skills_raw, str):
                skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
            else:
                skills = [t.get("label", "") for t in skills_raw]

            return JobDetail(
                id=job_id, title=title, company=company, location=location,
                salary=salary, skills_required=skills, url=url,
                description=description, experience_required=experience,
                posted_at=str(posted_at), found_at=datetime.now(),
                applicants=jd.get("applyCount"),
            )
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Profile
    # ------------------------------------------------------------------ #

    async def get_profile(self) -> NaukriProfile:
        await self.login()
        try:
            data = await self._get(PROFILE_URL)
        except Exception as e:
            raise NaukriError(f"Profile fetch failed: {e}")
        profiles = data.get("profile") or []
        p = profiles[0] if isinstance(profiles, list) and profiles else (profiles if isinstance(profiles, dict) else {})
        headline = p.get("resumeHeadline") or p.get("headline") or ""
        raw_skills = p.get("keySkills") or []
        skills = [
            s.get("label") or s.get("value") or s.get("keyword") or str(s)
            for s in (raw_skills if isinstance(raw_skills, list) else [])
        ]
        experience = p.get("employmentDetails") or p.get("experience") or []
        education = p.get("educationDetails") or p.get("education") or []
        return NaukriProfile(
            headline=headline,
            skills=skills,
            experience=experience if isinstance(experience, list) else [],
            education=education if isinstance(education, list) else [],
        )

    # ------------------------------------------------------------------ #
    # Resume upload
    # ------------------------------------------------------------------ #

    async def upload_resume(self, resume_path: str) -> bool:
        await self.login()
        try:
            with open(resume_path, "rb") as f:
                content = f.read()
            headers = self._request_headers({
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f'attachment; filename="{Path(resume_path).name}"',
            })
            resp = await self._client.post(
                RESUME_UPLOAD_URL, content=content,
                headers=headers, cookies=self._cookies,
            )
            return resp.status_code in (200, 201)
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Apply
    # ------------------------------------------------------------------ #

    async def apply_to_job(self, url: str, dry_run: bool = False) -> bool | dict:
        # Reset counter if it's a new day
        today = datetime.now().date()
        if today != self._session_date:
            self._applications_this_session = 0
            self._session_date = today
        if self._applications_this_session >= self.max_applications:
            raise NaukriError(
                f"Max applications per session ({self.max_applications}) reached."
            )
        await self.login()

        # Extract job ID from URL (last numeric segment)
        parts = url.rstrip("/").split("-")
        job_id = next((p for p in reversed(parts) if p.isdigit()), "")
        if not job_id:
            parts2 = url.rstrip("/").split("/")
            job_id = parts2[-1]

        if dry_run:
            return bool(job_id)

        apply_headers = {
            "appid": "121",
            "systemid": "jobseeker",
            "clientid": "d3skt0p",
        }
        base_payload = {
            "strJobsarr": [job_id],
            "logstr": "----F-0-1---",
            "crossdomain": True,
            "jquery": 1,
            "rdxMsgId": "",
            "chatBotSDK": True,
            "applyTypeId": "107",
            "closebtn": "y",
            "applySrc": "----F-0-1---",
            "sid": "",
            "mid": "",
        }

        # ---- Step 1: probe (flowtype=show) ----
        resp = await self._client.post(
            APPLY_URL, json={**base_payload, "flowtype": "show"},
            headers=self._request_headers(apply_headers),
            cookies=self._cookies,
        )
        # JWT token may have expired — force re-login and retry once
        if resp.status_code == 401:
            self._logged_in = False
            await self._login_email_password()
            resp = await self._client.post(
                APPLY_URL, json={**base_payload, "flowtype": "show"},
                headers=self._request_headers(apply_headers),
                cookies=self._cookies,
            )
        if resp.status_code not in (200, 201):
            try:
                err = resp.json()
                msg = err.get("message") or err.get("error") or str(err)
            except Exception:
                msg = resp.text or f"HTTP {resp.status_code}"
            raise NaukriError(f"Apply failed ({resp.status_code}): {msg}")

        try:
            data = resp.json()
        except Exception:
            # Empty body on 200 = successful apply with no questionnaire
            if resp.status_code in (200, 201) and not resp.text.strip():
                self._applications_this_session += 1
                return True
            raise NaukriError(f"Unexpected non-JSON apply response: {resp.text[:200]}")

        # Already-applied check
        apply_status = data.get("applyStatus", {})
        if apply_status.get(job_id) == 409001:
            raise NaukriError(f"Already applied to job {job_id}")

        # ---- Step 2: return questionnaire to caller if present ----
        jobs_list = data.get("jobs", [])
        job_entry = next((j for j in jobs_list if str(j.get("jobId")) == job_id), {})
        questionnaire = job_entry.get("questionnaire") or []

        if questionnaire:
            # Surface questions to the MCP caller (Claude) so they can be answered
            # intelligently — or the user can be asked for ambiguous ones.
            return {
                "needs_questionnaire": True,
                "job_id": job_id,
                "company": job_entry.get("companyName", ""),
                "job_title": job_entry.get("jobTitle", ""),
                "questions": questionnaire,
                "skippable_questions": data.get("skippableQuestions") or [],
                "instructions": (
                    "Answer each question using the candidate profile. "
                    "For anything ambiguous or unknown, ask the user before answering. "
                    "Then call submit_questionnaire with job_id and answers dict "
                    "{questionId: answerValue} where answerValue is the option KEY "
                    "(e.g. '3') for Radio/List questions or free text for Text Box."
                ),
            }

        # ---- Step 3: confirm result (no questionnaire) ----
        jobs_result = data.get("jobs", [])
        if jobs_result:
            job_result = next((j for j in jobs_result if str(j.get("jobId")) == job_id), None)
            if job_result:
                status = job_result.get("status")
                if status is not None and status != 200:
                    msg = job_result.get("message", "Unknown error")
                    raise NaukriError(f"Apply failed: {msg}")

        self._applications_this_session += 1
        return True

    async def submit_questionnaire(self, job_id: str, answers: dict, url: str) -> bool:
        """Submit questionnaire answers for a job that requires screening questions."""
        await self.login()

        parts = url.rstrip("/").split("-")
        extracted_id = next((p for p in reversed(parts) if p.isdigit()), job_id)

        apply_headers = {
            "appid": "121",
            "systemid": "jobseeker",
            "clientid": "d3skt0p",
        }
        base_payload = {
            "strJobsarr": [extracted_id],
            "logstr": "----F-0-1---",
            "crossdomain": True,
            "jquery": 1,
            "rdxMsgId": "",
            "chatBotSDK": True,
            "applyTypeId": "107",
            "closebtn": "y",
            "applySrc": "----F-0-1---",
            "sid": "",
            "mid": "",
        }
        resp = await self._client.post(
            APPLY_URL,
            json={
                **base_payload,
                "flowtype": "apply",
                "questionnaireResponse": {extracted_id: answers},
            },
            headers=self._request_headers(apply_headers),
            cookies=self._cookies,
        )
        # JWT token may have expired — force re-login and retry once
        if resp.status_code == 401:
            self._logged_in = False
            await self._login_email_password()
            resp = await self._client.post(
                APPLY_URL,
                json={
                    **base_payload,
                    "flowtype": "apply",
                    "questionnaireResponse": {extracted_id: answers},
                },
                headers=self._request_headers(apply_headers),
                cookies=self._cookies,
            )
        if resp.status_code not in (200, 201):
            try:
                err = resp.json()
                msg = err.get("message") or err.get("error") or str(err)
            except Exception:
                msg = resp.text or f"HTTP {resp.status_code}"
            raise NaukriError(f"Questionnaire submit failed ({resp.status_code}): {msg}")

        try:
            data = resp.json()
        except Exception:
            if resp.status_code in (200, 201) and not resp.text.strip():
                return True
            raise NaukriError(f"Unexpected non-JSON questionnaire response: {resp.text[:200]}")
        apply_status = data.get("applyStatus", {})
        if apply_status.get(extracted_id) == 409001:
            raise NaukriError(f"Already applied to job {extracted_id}")

        jobs_result = data.get("jobs", [])
        if jobs_result:
            job_result = next((j for j in jobs_result if str(j.get("jobId")) == extracted_id), None)
            if job_result:
                status = job_result.get("status")
                if status is not None and status != 200:
                    msg = job_result.get("message", "Unknown error")
                    raise NaukriError(f"Apply failed after questionnaire: {msg}")

        self._applications_this_session += 1
        return True

    # ------------------------------------------------------------------ #
    # Application status
    # ------------------------------------------------------------------ #

    def _parse_apply_result(self, job_id: str, data: dict) -> dict:
        """Parse apply API response and return structured result."""
        jobs_list = data.get("jobs", [])
        job_entry = next((j for j in jobs_list if str(j.get("jobId")) == job_id), {})
        status_code = job_entry.get("status")

        if status_code == 202:
            # Apply on company site
            external_url = job_entry.get("jdURL") or job_entry.get("redirectURL") or ""
            return {
                "apply_on_company_site": True,
                "external_url": external_url,
                "job_id": job_id,
                "message": f"This job requires applying on the company site: {external_url}",
            }

        if status_code == 409001 or data.get("applyStatus", {}).get(job_id) == 409001:
            raise NaukriError(f"Already applied to job {job_id}")

        if status_code is not None and status_code != 200:
            msg = job_entry.get("message", "Unknown error")
            raise NaukriError(f"Apply failed: {msg}")

        return {"success": True}

    def _parse_recruiter_status(self, entry: dict) -> str:
        """Normalize Naukri applyStatus string to our internal status."""
        raw = (entry.get("applyStatus") or entry.get("status") or "").lower()
        if "shortlist" in raw:
            return "shortlisted"
        if "reject" in raw or "not select" in raw:
            return "rejected"
        if "view" in raw or "seen" in raw:
            return "viewed"
        if "expir" in raw or "closed" in raw:
            return "expired"
        return "applied"

    async def fetch_application_statuses(self, job_ids: list[str]) -> dict[str, str]:
        """
        Fetch current recruiter status for a list of applied job IDs.
        Returns {job_id: recruiter_status}.
        Uses APPLY_HISTORY_URL constant (already in naukri.py).
        """
        await self.login()
        try:
            data = await self._get(
                APPLY_HISTORY_URL,
                params={"appPage": 1, "pageSize": 200},
            )
        except Exception as e:
            raise NaukriError(f"Could not fetch apply history: {e}")

        applications = (
            data.get("jobApplyList")
            or data.get("applications")
            or data.get("data")
            or []
        )

        id_set = set(str(j) for j in job_ids)
        result = {}
        for app in applications:
            jid = str(app.get("jobId") or app.get("id") or "")
            if jid in id_set:
                result[jid] = self._parse_recruiter_status(app)
        return result


# Alias so server.py import works unchanged
NaukriBrowser = NaukriClient

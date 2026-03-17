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
SEND_OTP_URL     = f"{NAUKRI_BASE}/central-login-services/v0/otp"
VERIFY_OTP_URL   = f"{NAUKRI_BASE}/central-login-services/v0/otp-login"
EMAIL_LOGIN_URL  = f"{NAUKRI_BASE}/central-login-services/v0/login"
LOGIN_STATUS_URL = f"{NAUKRI_BASE}/central-login-services/v0/credentials/login-status"
LOGOUT_URL       = f"{NAUKRI_BASE}/loginapi/v1/logout"

SEARCH_URL       = f"{NAUKRI_BASE}/jobapi/v3/search"
JOB_DETAIL_URL   = f"{NAUKRI_BASE}/jobapi/v4/job"
APPLY_URL        = f"{NAUKRI_BASE}/cloudgateway-workflow/workflow-services/apply-workflow/v1/apply"
APPLY_HISTORY_URL= f"{NAUKRI_BASE}/applyapi/webapphistory"

PROFILE_URL      = f"{NAUKRI_BASE}/jobseekerapi/v1/user"
RESUME_UPLOAD_URL= f"{NAUKRI_BASE}/mnjapi/v1/resume"

BASE_HEADERS = {
    "appid": "105",
    "systemid": "jobseeker",
    "Content-Type": "application/json",
    "Accept": "application/json",
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
            h["authorization"] = self._auth_token
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
            json={"username": self.phone, "flowId": "login"},
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
        if resp.status_code == 200 and data.get("userId"):
            self._auth_token = data.get("authToken") or data.get("jwtToken")
            self._cookies.update(dict(resp.cookies))
            self._otp_pending = False
            self._logged_in = True
            self._save_session()
        else:
            msg = data.get("message") or str(data)
            raise LoginError(f"OTP verification failed: {msg}")

    # ------------------------------------------------------------------ #
    # Job search
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
        params = {
            "noOfResults": max_results,
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": title,
            "location": location,
            "experience": experience,
            "k": title,
            "l": location,
        }
        if skills:
            params["skill"] = ",".join(skills)
        try:
            data = await self._get(SEARCH_URL, params=params)
        except Exception as e:
            raise NaukriError(f"Job search failed: {e}")
        jobs = []
        for item in (data.get("jobDetails") or [])[:max_results]:
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
            placeholders = item.get("placeholders") or []
            loc_str = ", ".join(
                p.get("label", "") for p in placeholders if p.get("type") == "location"
            )
            salary = next(
                (p.get("label") for p in placeholders if p.get("type") == "salary"), None
            )
            skills = [t.get("label", "") for t in (item.get("tagsAndSkills") or [])]
            url = item.get("jdURL") or f"{NAUKRI_BASE}/job-listings-{job_id}"
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
        await self.login()
        try:
            data = await self._get(f"{JOB_DETAIL_URL}/{job_id}")
        except Exception as e:
            raise NaukriError(f"Job details fetch failed: {e}")
        try:
            jd = data.get("jobDetails") or data
            title = jd.get("title") or jd.get("jobTitle") or ""
            company = jd.get("companyName") or ""
            if isinstance(company, dict):
                company = company.get("label") or ""
            placeholders = jd.get("placeholders") or []
            location = ", ".join(
                p.get("label", "") for p in placeholders if p.get("type") == "location"
            )
            salary = next(
                (p.get("label") for p in placeholders if p.get("type") == "salary"), None
            )
            description = jd.get("jobDescription") or jd.get("description") or ""
            experience = next(
                (p.get("label", "") for p in placeholders if p.get("type") == "experience"), ""
            )
            posted_at = jd.get("createdDate") or jd.get("postedOn") or ""
            skills = [t.get("label", "") for t in (jd.get("tagsAndSkills") or [])]
            return JobDetail(
                id=job_id, title=title, company=company, location=location,
                salary=salary, skills_required=skills, url=url,
                description=description, experience_required=experience,
                posted_at=str(posted_at), found_at=datetime.now(),
                applicants=jd.get("applicantCount"),
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
        headline = data.get("headline") or data.get("title") or ""
        skills = [
            s.get("label") or s.get("value") or str(s)
            for s in (data.get("keySkills") or data.get("skills") or [])
        ]
        experience = data.get("employmentDetails") or data.get("experience") or []
        education = data.get("educationDetails") or data.get("education") or []
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

    async def apply_to_job(self, url: str, dry_run: bool = False) -> bool:
        if self._applications_this_session >= self.max_applications:
            raise NaukriError(
                f"Max applications per session ({self.max_applications}) reached."
            )
        await self.login()

        # Extract job ID from URL  (last numeric segment)
        parts = url.rstrip("/").split("-")
        job_id = next((p for p in reversed(parts) if p.isdigit()), "")
        if not job_id:
            parts2 = url.rstrip("/").split("/")
            job_id = parts2[-1]

        if dry_run:
            try:
                data = await self._get(f"{JOB_DETAIL_URL}/{job_id}")
                return bool(data)
            except Exception:
                return False

        resp = await self._post(APPLY_URL, {"jobId": job_id})
        if resp.status_code in (200, 201):
            self._applications_this_session += 1
            return True
        data = resp.json()
        msg = data.get("message") or data.get("error") or str(data)
        raise NaukriError(f"Apply failed ({resp.status_code}): {msg}")


# Alias so server.py import works unchanged
NaukriBrowser = NaukriClient

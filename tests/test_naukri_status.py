# tests/test_naukri_status.py
from naukri import NaukriClient

def test_parse_recruiter_status_shortlisted():
    client = NaukriClient.__new__(NaukriClient)
    entry = {"applyStatus": "Shortlisted", "jobId": "123"}
    status = client._parse_recruiter_status(entry)
    assert status == "shortlisted"

def test_parse_recruiter_status_viewed():
    client = NaukriClient.__new__(NaukriClient)
    entry = {"applyStatus": "Viewed", "jobId": "123"}
    assert client._parse_recruiter_status(entry) == "viewed"

def test_parse_recruiter_status_rejected():
    client = NaukriClient.__new__(NaukriClient)
    entry = {"applyStatus": "Rejected", "jobId": "123"}
    assert client._parse_recruiter_status(entry) == "rejected"

def test_parse_recruiter_status_applied():
    client = NaukriClient.__new__(NaukriClient)
    entry = {"applyStatus": "Applied", "jobId": "123"}
    assert client._parse_recruiter_status(entry) == "applied"

def test_parse_apply_result_company_site():
    client = NaukriClient.__new__(NaukriClient)
    # status 202 means "apply on company site"
    job_entry = {"jobId": "123", "status": 202, "jdURL": "https://company.com/apply"}
    result = client._parse_apply_result("123", {"jobs": [job_entry]})
    assert result["apply_on_company_site"] is True
    assert "https://company.com/apply" in result["external_url"]

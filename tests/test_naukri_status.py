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

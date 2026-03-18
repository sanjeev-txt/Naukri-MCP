# tests/test_auto_questionnaire.py
import pytest
from server import NaukriMCPServer
from models import CandidateProfile
from unittest.mock import MagicMock

def make_server():
    s = NaukriMCPServer.__new__(NaukriMCPServer)
    s.candidate_profile = CandidateProfile(
        current_ctc=8, expected_ctc=14, notice_period_days=60,
        total_experience_years=4, current_location="Faridabad",
        willing_to_relocate=True, skills=["Python", "FastAPI", "LangChain"]
    )
    return s

def test_auto_answer_ctc():
    s = make_server()
    q = {"questionId": "q1", "type": "Text Box", "question": "What is your current CTC in Lacs?"}
    ans = s._auto_answer_question(q)
    assert ans == "8"

def test_auto_answer_experience():
    s = make_server()
    q = {"questionId": "q2", "type": "Text Box", "question": "How many years of Python experience do you have?"}
    ans = s._auto_answer_question(q)
    assert ans == "4"

def test_auto_answer_notice():
    s = make_server()
    q = {"questionId": "q3", "type": "Text Box", "question": "What is your notice period in days?"}
    ans = s._auto_answer_question(q)
    assert ans == "60"

def test_auto_answer_relocate_yes():
    s = make_server()
    q = {"questionId": "q4", "type": "Radio Button", "question": "Are you willing to relocate to Gurugram?",
         "options": [{"optionId": "1", "option": "Yes"}, {"optionId": "2", "option": "No"}]}
    ans = s._auto_answer_question(q)
    assert ans == "1"  # Yes option key

def test_auto_answer_unknown_returns_none():
    s = make_server()
    q = {"questionId": "q5", "type": "Text Box", "question": "Describe your thesis on distributed systems"}
    ans = s._auto_answer_question(q)
    assert ans is None  # cannot auto-answer

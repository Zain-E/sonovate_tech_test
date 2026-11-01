from datetime import datetime

from reporting.answers import render

BASE = {
    "searched_at": datetime(2026, 11, 1, 9, 0),
    "total_results": 2500,
    "results_fetched": 1000,
    "is_truncated": True,
    "active_companies": 600,
    "dissolved_companies": 0,
    "avg_dissolved_lifespan_days": None,
    "first_limited_partnership_incorporated_on": None,
    "first_limited_partnership_name": None,
    "title_matches": [],
    "premises": [],
}


def test_flags_when_the_api_cap_truncated_the_results():
    md = render(BASE, "sono", "vate")
    assert "reports 2,500 matches" in md
    assert "cover the 1,000 companies fetched" in md


def test_handles_questions_with_no_qualifying_companies():
    md = render(BASE, "sono", "vate")
    assert "dissolved companies:** n/a" in md
    assert "First limited partnership created:** n/a" in md
    assert "_None._" in md

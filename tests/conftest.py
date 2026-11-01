import json
from pathlib import Path

import pytest

from ingestion.companies_house import BASE_URL, MAX_RESULTS

FIXTURES = Path(__file__).parent / "fixtures"


def fake_company(n: int) -> dict:
    return {"company_number": f"{n:08d}", "title": f"SONO COMPANY {n} LIMITED"}


@pytest.fixture
def mock_search(requests_mock):
    """Serve a fake /search/companies that pages like the real API (incl. the 1,000 cap)."""

    def register(items: list[dict], total_results: int | None = None):
        total = len(items) if total_results is None else total_results

        def respond(request, context):
            start = int(request.qs.get("start_index", ["0"])[0])
            size = min(int(request.qs.get("items_per_page", ["20"])[0]), 100)
            if start >= MAX_RESULTS:
                context.status_code = 416
                return {"error": "start_index too high"}
            return {
                "items": items[start : start + size],
                "total_results": total,
                "start_index": start,
                "items_per_page": size,
            }

        return requests_mock.get(f"{BASE_URL}/search/companies", json=respond)

    return register


@pytest.fixture(scope="session")
def sono_fixture() -> dict:
    return json.loads((FIXTURES / "search_companies_sono.json").read_text())


@pytest.fixture(scope="session")
def psc_fixture() -> dict:
    """PSCs of sono company 00000001: one current individual, one ceased corporate."""
    return json.loads((FIXTURES / "psc_00000001.json").read_text())

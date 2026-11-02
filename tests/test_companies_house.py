import base64
from datetime import UTC, datetime

import pytest
from requests import HTTPError

from ingestion import companies_house
from ingestion.companies_house import (
    BASE_URL,
    count_companies,
    list_persons_with_significant_control,
    make_client,
    psc_fetch_due,
    search_companies,
)
from tests.conftest import fake_company

PSC_URL = f"{BASE_URL}/company/00000001/persons-with-significant-control"


@pytest.fixture
def client():
    return make_client("test-key")


def test_pages_through_all_results_and_ranks_them(client, mock_search):
    mock = mock_search([fake_company(n) for n in range(250)])

    results = list(search_companies(client, "sono"))

    assert [r["search_rank"] for r in results] == list(range(1, 251))
    assert {r["search_term"] for r in results} == {"sono"}
    assert mock.call_count == 3


def test_requests_100_per_page(client, mock_search):
    mock = mock_search([fake_company(n) for n in range(150)])

    list(search_companies(client, "sono"))

    assert [r.qs["items_per_page"] for r in mock.request_history] == [["100"], ["100"]]
    assert [r.qs["start_index"] for r in mock.request_history] == [["0"], ["100"]]


def test_stops_at_the_api_cap(client, mock_search):
    mock = mock_search([fake_company(n) for n in range(2500)])

    results = list(search_companies(client, "sono"))

    assert len(results) == 1000
    assert mock.call_count == 10  # never requests start_index >= 1000, which would error


def test_count_reports_the_true_total_beyond_the_cap(client, mock_search):
    mock = mock_search([fake_company(n) for n in range(2500)])

    summary = count_companies(client, "sono")

    assert summary["search_term"] == "sono"
    assert summary["total_results"] == 2500
    assert mock.last_request.qs["items_per_page"] == ["1"]


def test_no_results(client, mock_search):
    mock_search([])

    assert list(search_companies(client, "sono")) == []
    assert count_companies(client, "sono")["total_results"] == 0


def test_authenticates_with_api_key_as_basic_auth_username(client, mock_search):
    mock = mock_search([fake_company(1)])

    count_companies(client, "sono")
    list(search_companies(client, "sono"))

    expected = "Basic " + base64.b64encode(b"test-key:").decode()
    assert [r.headers["Authorization"] for r in mock.request_history] == [expected, expected]


def test_retries_when_rate_limited(client, requests_mock, sono_fixture):
    requests_mock.get(
        f"{BASE_URL}/search/companies",
        [{"status_code": 429, "headers": {"Retry-After": "0"}}, {"json": sono_fixture}],
    )

    results = list(search_companies(client, "sono"))

    assert len(results) == len(sono_fixture["items"])
    assert requests_mock.call_count == 2


def test_raises_on_bad_api_key(client, requests_mock):
    requests_mock.get(f"{BASE_URL}/search/companies", status_code=401)

    with pytest.raises(HTTPError):
        count_companies(client, "sono")


def test_lists_pscs_tagged_with_their_company(client, requests_mock, psc_fixture):
    requests_mock.get(PSC_URL, json=psc_fixture)

    pscs = list(list_persons_with_significant_control(client, "00000001"))

    assert [p["name"] for p in pscs] == ["Ms Jane Example", "Example Holdings Limited"]
    assert {p["company_number"] for p in pscs} == {"00000001"}
    assert not any("etag" in p for p in pscs)  # changes on its own; would churn SCD2 versions
    assert requests_mock.last_request.qs["items_per_page"] == ["100"]


def test_company_without_a_psc_record_yields_nothing(client, requests_mock):
    requests_mock.get(PSC_URL, status_code=404)

    assert list(list_persons_with_significant_control(client, "00000001")) == []


def test_psc_errors_other_than_not_found_raise(client, requests_mock):
    requests_mock.get(PSC_URL, status_code=401)

    with pytest.raises(HTTPError):
        list(list_persons_with_significant_control(client, "00000001"))


@pytest.mark.parametrize(("remaining", "expect_wait"), [("11", False), ("10", True), ("0", True)])
def test_waits_for_the_rate_limit_window_when_quota_runs_low(
    client, requests_mock, psc_fixture, monkeypatch, remaining, expect_wait
):
    sleeps = []
    monkeypatch.setattr(companies_house.time, "time", lambda: 1_000)
    monkeypatch.setattr(companies_house.time, "sleep", sleeps.append)
    headers = {"X-Ratelimit-Remain": remaining, "X-Ratelimit-Reset": "1060"}
    requests_mock.get(PSC_URL, json=psc_fixture, headers=headers)

    list(list_persons_with_significant_control(client, "00000001"))

    assert sleeps == ([61] if expect_wait else [])


NOW = datetime(2026, 11, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    ("last_fetch", "refresh_days", "due"),
    [
        (None, 7, True),  # new company
        ({"version": "old", "fetched_at": "2026-11-07T00:00:00+00:00"}, 7, True),  # changed
        ({"version": "v1", "fetched_at": "2026-11-07T00:00:00+00:00"}, 7, False),  # fresh
        ({"version": "v1", "fetched_at": "2026-11-01T00:00:00+00:00"}, 7, True),  # stale
        ({"version": "v1", "fetched_at": "2026-11-08T00:00:00+00:00"}, 0, True),  # full refresh
    ],
)
def test_psc_fetch_due(last_fetch, refresh_days, due):
    assert psc_fetch_due(last_fetch, "v1", NOW, refresh_days) is due

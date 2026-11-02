"""Given recorded API responses, the whole pipeline (dlt -> dbt) gets the answers right
and keeps history across runs.

Fixtures: tests/fixtures/search_companies_sono.json (7 synthetic companies) and
psc_00000001.json (the PSCs of one of them; every other company has no PSC record). The pipeline
runs three times: against an earlier state of the API (see `earlier`), then against the fixtures
with the default PSC refresh window, then again with a full PSC refresh.
"""

import copy
import re
from datetime import date
from pathlib import Path

import duckdb
import pytest
import requests_mock
from dbt.cli.main import dbtRunner

from ingestion import pipeline
from ingestion.companies_house import BASE_URL

TRANSFORM_DIR = Path(__file__).parents[1] / "transform"


def earlier(sono_fixture: dict, psc_fixture: dict) -> tuple[dict, dict]:
    """The API before the fixtures' state: 00000002 was still active, SONO GONE LTD was still
    returned, and the corporate PSC of 00000001 had not yet ceased."""
    search, psc = copy.deepcopy(sono_fixture), copy.deepcopy(psc_fixture)
    renovate = next(c for c in search["items"] if c["company_number"] == "00000002")
    renovate["company_status"] = "active"
    del renovate["date_of_cessation"]
    gone = {"company_number": "00000099", "title": "SONO GONE LTD", "company_status": "active"}
    search["items"].append({**gone, "company_type": "ltd", "date_of_creation": "2020-01-01"})
    search["total_results"] += 1
    corporate = psc["items"][1]
    corporate["ceased"] = False
    del corporate["ceased_on"]
    return search, psc


def load(api: requests_mock.Mocker, db: str, search: dict, psc: dict, **kwargs) -> list[str]:
    """Run the pipeline against these responses; return the companies whose PSCs it fetched."""
    api.reset_mock()
    api.get(f"{BASE_URL}/search/companies", json=search)
    api.get(
        re.compile(rf"{BASE_URL}/company/\w+/persons-with-significant-control"), status_code=404
    )
    api.get(f"{BASE_URL}/company/00000001/persons-with-significant-control", json=psc)
    pipeline.run(db, search_terms=["sono"], api_key="test-key", **kwargs)
    return sorted(
        r.path.split("/")[2].upper() for r in api.request_history if "/company/" in r.path
    )


@pytest.fixture(scope="module")
def runs(tmp_path_factory, sono_fixture, psc_fixture):
    tmp = tmp_path_factory.mktemp("warehouse")
    db = str(tmp / "warehouse.duckdb")

    with pytest.MonkeyPatch.context() as env, requests_mock.Mocker() as api:
        env.setenv("DLT_DATA_DIR", str(tmp / "dlt"))
        env.setenv("DUCKDB_PATH", db)
        psc_fetches = [
            load(api, db, *earlier(sono_fixture, psc_fixture)),
            load(api, db, sono_fixture, psc_fixture),
            load(api, db, sono_fixture, psc_fixture, psc_refresh_days=0),
        ]
        yield {"tmp": tmp, "db": db, "psc_fetches": psc_fetches}


@pytest.fixture(scope="module")
def warehouse(runs):
    # dbt finds the database through DUCKDB_PATH, which `runs` keeps set for the module.
    dbt = dbtRunner().invoke(
        [
            "build",
            "--project-dir",
            str(TRANSFORM_DIR),
            "--profiles-dir",
            str(TRANSFORM_DIR),
            "--target-path",
            str(runs["tmp"] / "target"),
            "--quiet",
        ]
    )
    assert dbt.success, dbt.exception

    # not read_only: dbt-duckdb still holds a read-write handle
    with duckdb.connect(runs["db"]) as con:
        yield con


@pytest.fixture(scope="module")
def summary(warehouse) -> dict:
    """The analytics row behind the dashboard's Q1-Q4 scorecards."""
    cursor = warehouse.execute("select * from analytics.search_summary where search_term = 'sono'")
    return dict(zip([col[0] for col in cursor.description], cursor.fetchone(), strict=True))


def test_q1_counts_every_company_the_api_matched(summary):
    assert summary["total_results"] == summary["results_fetched"] == 7
    assert not summary["is_truncated"]


def test_q2_counts_active_companies(summary):
    assert summary["active_companies"] == 3


def test_q3_averages_dissolved_company_lifespans(summary):
    # 730 (2010-01-01 -> 2012-01-01) + 366 (leap year) + 2557 (1998-07-20 -> 2005-07-20)
    assert summary["avg_dissolved_lifespan_days"] == pytest.approx((730 + 366 + 2557) / 3)


def test_q4_finds_the_first_limited_partnership(summary):
    assert summary["first_limited_partnership_incorporated_on"] == date(1998, 7, 20)
    assert summary["first_limited_partnership_name"] == "SONO HOLDINGS LP"


def test_q5_finds_names_also_containing_vate(warehouse):
    names = warehouse.sql(
        """
        select company_name from analytics.search_companies
        where search_term = 'sono' and company_name ilike '%vate%'
        order by 1
        """
    ).fetchall()

    assert names == [("SONO RENOVATE LTD",), ("SONOVATECH LIMITED",)]


def test_q6_sums_premises_digits_by_company_type(warehouse):
    sums = warehouse.sql(
        """
        select company_type, premises_number_sum from analytics.search_premises_by_company_type
        where search_term = 'sono'
        """
    ).fetchall()

    # ltd: '6-8' + '14b' + '1st Floor 45 Main St' + '100' = 68 + 14 + 145 + 100
    assert dict(sums) == {"ltd": 327, "limited-partnership": 2, "llp": 0}


def test_dim_psc_flattens_each_person_with_significant_control(warehouse):
    rows = warehouse.sql(
        """
        select psc_id, company_number, psc_kind, surname, birth_year, natures_of_control,
               ceased_on, is_ceased, registration_number
        from warehouse.warehouse.dim_person_with_significant_control  -- db file is also "warehouse"
        order by psc_id
        """
    ).fetchall()

    assert rows == [
        (
            "PSC-CORPORATE-1",
            "00000001",
            "corporate-entity-person-with-significant-control",
            None,
            None,
            ["ownership-of-shares-25-to-50-percent"],
            date(2020, 1, 31),
            True,
            "99999999",
        ),
        (
            "PSC-INDIVIDUAL-1",
            "00000001",
            "individual-person-with-significant-control",
            "Example",
            1975,
            ["ownership-of-shares-75-to-100-percent", "voting-rights-75-to-100-percent"],
            None,
            False,
            None,
        ),
    ]


def test_answers_come_from_the_latest_run_only(warehouse):
    snapshots = warehouse.sql(
        "select total_results, is_latest_snapshot from warehouse.warehouse.fct_company_searches"
        " order by loaded_at"
    ).fetchall()

    assert snapshots == [(8, False), (7, False), (7, True)]


def test_company_history_versions_changes_and_closes_companies_no_longer_returned(warehouse):
    versions = warehouse.sql(
        """
        select company_number, company_status, valid_to is not null as is_closed, is_current
        from warehouse.warehouse.dim_company_history
        where company_number in ('00000001', '00000002', '00000099')
        order by company_number, valid_from
        """
    ).fetchall()

    assert versions == [
        ("00000001", "active", False, True),  # unchanged: still its first version
        ("00000002", "active", True, False),
        ("00000002", "dissolved", False, True),
        ("00000099", "active", True, False),  # no longer returned by the search
    ]
    current = warehouse.sql("select count(*) from warehouse.warehouse.dim_company").fetchone()
    assert current == (7,)


def test_psc_extraction_is_incremental(runs):
    first, second, full_refresh = runs["psc_fetches"]

    assert len(first) == 8  # every company returned, including SONO GONE LTD
    assert second == ["00000002"]  # the only company whose attributes changed
    assert len(full_refresh) == 7  # psc_refresh_days=0 re-fetches every company returned


def test_psc_history_versions_a_psc_when_it_ceases(warehouse):
    # The corporate PSC ceased before run 2, but 00000001 was unchanged, so it was only seen on the
    # full refresh. Run 2 must not have closed the PSCs of companies it didn't fetch.
    versions = warehouse.sql(
        """
        select psc_id, ceased_on, is_current
        from warehouse.warehouse.dim_person_with_significant_control_history
        order by psc_id, valid_from
        """
    ).fetchall()

    assert versions == [
        ("PSC-CORPORATE-1", None, False),
        ("PSC-CORPORATE-1", date(2020, 1, 31), True),
        ("PSC-INDIVIDUAL-1", None, True),
    ]


def test_dashboard_psc_mart_lists_each_searched_companys_pscs(warehouse):
    rows = warehouse.sql(
        """
        select company_name, psc_id, is_ceased
        from analytics.search_persons_with_significant_control
        where search_term = 'sono'
        order by psc_id
        """
    ).fetchall()

    assert rows == [
        ("SONOVATECH LIMITED", "PSC-CORPORATE-1", True),
        ("SONOVATECH LIMITED", "PSC-INDIVIDUAL-1", False),
    ]


def test_explore_dataset_has_each_companys_latest_psc(warehouse):
    rows = warehouse.sql(
        """
        select company_number, psc_id
        from analytics.search_companies_with_pscs
        where search_term = 'sono'
        order by company_number
        """
    ).fetchall()

    assert len(rows) == 7  # one row per company
    # 00000001's corporate PSC has ceased, so its individual PSC (still in control) is the latest.
    assert rows[:2] == [("00000001", "PSC-INDIVIDUAL-1"), ("00000002", None)]

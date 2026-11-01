"""Given recorded API responses, the whole pipeline (dlt -> dbt -> answers) gets the answers right
and keeps history across runs.

Fixtures: tests/fixtures/search_companies_sono.json (7 synthetic companies) and
psc_00000001.json (the PSCs of one of them; every other company has no PSC record). The pipeline
runs twice: first against an earlier state of the API (see `earlier`), then against the fixtures.
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
from reporting.answers import get_answers, render

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


def load(api: requests_mock.Mocker, db: str, search: dict, psc: dict) -> None:
    api.get(f"{BASE_URL}/search/companies", json=search)
    api.get(
        re.compile(rf"{BASE_URL}/company/\w+/persons-with-significant-control"), status_code=404
    )
    api.get(f"{BASE_URL}/company/00000001/persons-with-significant-control", json=psc)
    pipeline.run(db, search_terms=["sono"], api_key="test-key")


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory, sono_fixture, psc_fixture):
    tmp = tmp_path_factory.mktemp("warehouse")
    db = str(tmp / "warehouse.duckdb")

    with pytest.MonkeyPatch.context() as env, requests_mock.Mocker() as api:
        env.setenv("DLT_DATA_DIR", str(tmp / "dlt"))
        env.setenv("DUCKDB_PATH", db)

        load(api, db, *earlier(sono_fixture, psc_fixture))
        load(api, db, sono_fixture, psc_fixture)
        dbt = dbtRunner().invoke(
            [
                "build",
                "--project-dir",
                str(TRANSFORM_DIR),
                "--profiles-dir",
                str(TRANSFORM_DIR),
                "--target-path",
                str(tmp / "target"),
                "--quiet",
            ]
        )
        assert dbt.success, dbt.exception

    # not read_only: dbt-duckdb still holds a read-write handle
    with duckdb.connect(db) as con:
        yield con


@pytest.fixture(scope="module")
def answers(warehouse):
    return get_answers(warehouse, "sono", "vate")


def test_q1_counts_every_company_the_api_matched(answers):
    assert answers["total_results"] == answers["results_fetched"] == 7
    assert not answers["is_truncated"]


def test_q2_counts_active_companies(answers):
    assert answers["active_companies"] == 3


def test_q3_averages_dissolved_company_lifespans(answers):
    # 730 (2010-01-01 -> 2012-01-01) + 366 (leap year) + 2557 (1998-07-20 -> 2005-07-20)
    assert answers["avg_dissolved_lifespan_days"] == pytest.approx((730 + 366 + 2557) / 3)


def test_q4_finds_the_first_limited_partnership(answers):
    assert answers["first_limited_partnership_incorporated_on"] == date(1998, 7, 20)
    assert answers["first_limited_partnership_name"] == "SONO HOLDINGS LP"


def test_q5_finds_names_also_containing_vate(answers):
    names = [c["company_name"] for c in answers["title_matches"]]
    assert names == ["SONO RENOVATE LTD", "SONOVATECH LIMITED"]


def test_q6_sums_premises_digits_by_company_type(answers):
    sums = {r["company_type"]: r["premises_number_sum"] for r in answers["premises"]}
    # ltd: '6-8' + '14b' + '1st Floor 45 Main St' + '100' = 68 + 14 + 145 + 100
    assert sums == {"ltd": 327, "limited-partnership": 2, "llp": 0}


def test_renders_markdown(answers):
    md = render(answers, "sono", "vate")
    assert "**Active:** 3" in md
    assert "1998-07-20 (SONO HOLDINGS LP)" in md
    assert "| ltd | 327 | 4 | 4 |" in md


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
    runs = warehouse.sql(
        "select total_results, is_latest_snapshot from warehouse.warehouse.fct_company_searches"
        " order by loaded_at"
    ).fetchall()

    assert runs == [(8, False), (7, True)]


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


def test_psc_history_versions_a_psc_when_it_ceases(warehouse):
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

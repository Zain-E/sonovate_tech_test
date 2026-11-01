"""Given a recorded API response, the whole pipeline (dlt -> dbt -> answers) gets the answers right.

Fixtures: tests/fixtures/search_companies_sono.json (7 synthetic companies) and
psc_00000001.json (the PSCs of one of them; every other company has no PSC record).
"""

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


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory, sono_fixture, psc_fixture):
    tmp = tmp_path_factory.mktemp("warehouse")
    db = str(tmp / "warehouse.duckdb")

    with pytest.MonkeyPatch.context() as env, requests_mock.Mocker() as api:
        env.setenv("DLT_DATA_DIR", str(tmp / "dlt"))
        env.setenv("DUCKDB_PATH", db)
        api.get(f"{BASE_URL}/search/companies", json=sono_fixture)
        api.get(
            re.compile(rf"{BASE_URL}/company/\w+/persons-with-significant-control"), status_code=404
        )
        api.get(f"{BASE_URL}/company/00000001/persons-with-significant-control", json=psc_fixture)

        pipeline.run(db, search_terms=["sono"], api_key="test-key")
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

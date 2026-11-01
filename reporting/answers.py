"""Answer the tech-test questions from the analytics layer and write ANSWERS.md.

Usage: python -m reporting.answers [--term sono] [--title-contains vate] [--out ANSWERS.md]
"""

import argparse
import os
from pathlib import Path

import duckdb

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")


def _records(con: duckdb.DuckDBPyConnection, sql: str, *params) -> list[dict]:
    """Rows as dicts of native Python types (pandas would turn HUGEINT sums into floats)."""
    cursor = con.execute(sql, list(params))
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def get_answers(con: duckdb.DuckDBPyConnection, term: str, title_contains: str) -> dict:
    summary = _records(con, "select * from analytics.search_summary where search_term = ?", term)
    if not summary:
        raise ValueError(f"No search for {term!r}: add it to .dlt/config.toml and re-run.")

    title_matches = _records(
        con,
        """
        select company_number, company_name, company_status
        from analytics.search_companies
        where search_term = ? and company_name ilike '%' || ? || '%'
        order by company_name
        """,
        term,
        title_contains,
    )
    premises = _records(
        con,
        """
        select company_type, premises_number_sum, companies, companies_with_premises_number
        from analytics.search_premises_by_company_type
        where search_term = ?
        order by premises_number_sum desc, company_type
        """,
        term,
    )
    return {**summary[0], "title_matches": title_matches, "premises": premises}


def _table(records: list[dict]) -> str:
    if not records:
        return "_None._"
    header = list(records[0])
    rows = [header, ["---"] * len(header), *([str(r[c]) for c in header] for r in records)]
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def render(a: dict, term: str, title_contains: str) -> str:
    avg_life = a["avg_dissolved_lifespan_days"]
    first_lp = a["first_limited_partnership_incorporated_on"]
    caveat = (
        f"\n> The API reports {a['total_results']:,} matches but only lets you page through the "
        f"first 1,000, so Q2–Q6 cover the {a['results_fetched']:,} companies fetched.\n"
        if a["is_truncated"]
        else ""
    )
    return f"""# Answers: companies matching "{term}"

_Generated from the warehouse on {a["searched_at"]:%Y-%m-%d %H:%M} UTC by `make run`._
{caveat}
1. **Companies matching "{term}":** {a["total_results"]:,} ({a["results_fetched"]:,} fetched)
2. **Active:** {a["active_companies"]:,}
3. **Average life of dissolved companies:** \
{"n/a" if avg_life is None else f"{avg_life:,.2f} days"} \
(across {a["dissolved_companies"]:,} dissolved companies)
4. **First limited partnership created:** \
{"n/a" if first_lp is None else f"{first_lp:%Y-%m-%d} ({a['first_limited_partnership_name']})"}
5. **Companies also containing "{title_contains}" in their name:** {len(a["title_matches"])}

{_table(a["title_matches"])}

6. **Sum of premises digits by company type:**

{_table(a["premises"])}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", default="sono")
    parser.add_argument("--title-contains", default="vate")
    parser.add_argument("--out", default="ANSWERS.md")
    args = parser.parse_args()

    with duckdb.connect(DUCKDB_PATH, read_only=True) as con:
        answers = get_answers(con, args.term, args.title_contains)
    Path(args.out).write_text(render(answers, args.term, args.title_contains))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

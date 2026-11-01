"""Explore the analytics layer. Run: make app"""

import os

import duckdb
import pandas as pd
import streamlit as st

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DUCKDB_PATH, read_only=True)


def query(sql: str, *params) -> pd.DataFrame:
    return connection().cursor().execute(sql, list(params)).df()


st.set_page_config(page_title="Companies House search", page_icon="🏢", layout="wide")

terms = query("select search_term from analytics.search_summary order by 1").search_term
term = st.sidebar.selectbox("Search term", terms)
s = query("select * from analytics.search_summary where search_term = ?", term).iloc[0]
companies = query(
    "select * from analytics.search_companies where search_term = ? order by search_rank", term
)

st.title(f'Companies matching "{term}"')
st.caption(f"Searched {s.searched_at:%d %b %Y %H:%M} UTC")
if s.is_truncated:
    st.warning(
        f"The API reports {s.total_results:,} matches but only returns the first 1,000; "
        f"everything below covers the {s.results_fetched:,} fetched."
    )

q1, q2, q3, q4 = st.columns(4)
q1.metric("Q1 · Matching companies", f"{s.total_results:,}")
q2.metric("Q2 · Active", f"{s.active_companies:,}")
q3.metric(
    "Q3 · Avg dissolved lifespan",
    "–" if pd.isna(s.avg_dissolved_lifespan_days) else f"{s.avg_dissolved_lifespan_days:,.0f} days",
    help=f"Across {s.dissolved_companies:,} dissolved companies",
)
q4.metric(
    "Q4 · First limited partnership",
    "–"
    if pd.isna(s.first_limited_partnership_incorporated_on)
    else f"{s.first_limited_partnership_incorporated_on:%d %b %Y}",
    help=s.first_limited_partnership_name,
)

left, right = st.columns(2)
with left:
    st.subheader("Q5 · Names also containing…")
    needle = st.text_input("Text", value="vate", label_visibility="collapsed")
    matches = companies[companies.company_name.str.contains(needle, case=False, regex=False)]
    st.dataframe(
        matches[["company_number", "company_name", "company_status", "incorporated_on"]],
        hide_index=True,
    )
with right:
    st.subheader("Q6 · Sum of premises digits by company type")
    premises = query(
        "select * from analytics.search_premises_by_company_type where search_term = ?", term
    )
    st.bar_chart(
        premises,
        x="company_type_description",
        y="premises_number_sum",
        x_label="",  # with horizontal=True, x is the category axis
        y_label="Sum of premises digits",
        horizontal=True,
        height=300,
    )

st.subheader("Explore")
by_status, by_year = st.columns(2)
with by_status:
    st.caption("Companies by status")
    st.bar_chart(
        companies.company_status_description.value_counts(),
        horizontal=True,
        x_label="",
        y_label="Companies",
        height=300,
    )
with by_year:
    st.caption("Incorporations by year")
    years = pd.to_datetime(companies.incorporated_on).dt.year.astype("string")
    st.bar_chart(companies.groupby(years).size(), x_label="", y_label="Companies", height=300)

st.dataframe(companies.drop(columns="search_term"), hide_index=True)

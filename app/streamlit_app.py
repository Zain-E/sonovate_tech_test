"""Answer the tech-test questions from the analytics layer. Run: make app"""

import html
import os

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")

# Sonovate brand colours (theme in .streamlit/config.toml).
RICH_PURPLE = "#3D0066"
ELECTRIC_BLUE = "#01E1FD"
TEXT = "#180028"
MUTED = "#6E6877"
PURPLE_TINT = "#F6F3F9"

STYLE = f"""
<style>
h1, h2, h3 {{ color: {RICH_PURPLE}; }}
.cards {{ display: grid; gap: 1rem; margin-bottom: 1rem; }}
@media (max-width: 760px) {{ .cards {{ grid-template-columns: 1fr !important; }} }}
.scorecard {{
    background: {PURPLE_TINT};
    border-left: 6px solid {ELECTRIC_BLUE};
    border-radius: 0.75rem;
    padding: 1.1rem 1.5rem;
}}
.scorecard .title {{
    color: {RICH_PURPLE}; font-size: 1.1rem; font-weight: 700; margin-bottom: 0.6rem;
}}
.scorecard .value {{ color: {RICH_PURPLE}; font-size: 2.6rem; font-weight: 700; line-height: 1.1; }}
.scorecard .detail {{ color: {MUTED}; font-size: 0.95rem; margin-top: 0.3rem; }}
</style>
"""


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DUCKDB_PATH, read_only=True)


def query(sql: str, *params) -> pd.DataFrame:
    return connection().cursor().execute(sql, list(params)).df()


DATE_COLUMNS = ("incorporated_on", "ceased_on", "psc_notified_on", "psc_ceased_on")


def table(data: pd.DataFrame) -> None:
    """A table with readable headers ('company_number' -> 'company number') and dates without
    times (DuckDB dates arrive in pandas as timestamps)."""
    readable = data.rename(columns=lambda col: col.replace("_", " "))
    dates = {
        col.replace("_", " "): st.column_config.DateColumn(format="D MMM YYYY")
        for col in DATE_COLUMNS
    }
    st.dataframe(readable, hide_index=True, column_config=dates)


def scorecard(title: str, value: str, detail: str = "") -> str:
    """A single-figure answer: its title, the figure large, and one line of context."""
    return (
        f'<div class="scorecard"><div class="title">{html.escape(title)}</div>'
        f'<div class="value">{html.escape(value)}</div>'
        f'<div class="detail">{html.escape(detail)}</div></div>'
    )


def card_grid(cards: list[str], columns: int) -> None:
    """Scorecards in a grid of equal-height cells (one column on narrow screens)."""
    st.markdown(
        f'<div class="cards" style="grid-template-columns: repeat({columns}, 1fr)">'
        f"{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def bar_chart(data: pd.DataFrame, category: str, value: str) -> alt.Chart:
    """Horizontal bars labelled with their values; the value axis is hidden because the labels
    replace it."""
    # Headroom past the longest bar so its label isn't clipped.
    scale = alt.Scale(domain=[0, max(float(data[value].max()), 1) * 1.15])
    category_axis = alt.Axis(title=None, ticks=False, domain=False, labelLimit=260)
    bars = (
        alt.Chart(data)
        .mark_bar(color=RICH_PURPLE, cornerRadiusEnd=4)
        .encode(
            alt.Y(f"{category}:N", sort="-x", axis=category_axis),
            alt.X(f"{value}:Q", axis=None, scale=scale),
            tooltip=[category, value],
        )
    )
    labels = bars.mark_text(
        color=TEXT, fontWeight=600, align="left", baseline="middle", dx=4
    ).encode(text=alt.Text(f"{value}:Q", format=","))
    return (bars + labels).properties(height=max(120, 32 * len(data))).configure_view(strokeWidth=0)


st.set_page_config(page_title="Sonovate Companies House", page_icon="🏢", layout="wide")
st.markdown(STYLE, unsafe_allow_html=True)

# The pipeline is configured with one search term (.dlt/config.toml), so there is no selector.
term = query("select search_term from analytics.search_summary order by 1").search_term.iloc[0]
s = query("select * from analytics.search_summary where search_term = ?", term).iloc[0]
companies = query(
    "select * from analytics.search_companies where search_term = ? order by search_rank", term
)

st.title("Sonovate Companies House")
st.markdown(f"All data is extracted based on the search term **'{term}'**.")
st.caption(f"Searched {s.searched_at:%d %b %Y %H:%M} UTC")

active_share = s.active_companies / s.results_fetched if s.results_fetched else 0
days = s.avg_dissolved_lifespan_days
first_lp = s.first_limited_partnership_incorporated_on
card_grid(
    [
        scorecard(
            f'Q1 - Companies with the title "{term.upper()}"',
            f"{s.total_results:,}",
            f"{s.results_fetched:,} fetched from the API",
        ),
        scorecard(
            "Q2 - Of those, how many companies are active",
            f"{s.active_companies:,}",
            f"{active_share:.0%} of the {s.results_fetched:,} fetched",
        ),
        scorecard(
            "Q3 - Lifespan of dissolved companies",
            "–" if pd.isna(days) else f"{days:,.0f} days",
            "No dissolved companies"
            if pd.isna(days)
            else f"Average, about {days / 365.25:.1f} years, "
            f"across {s.dissolved_companies:,} dissolved companies",
        ),
        scorecard(
            "Q4 - The first Limited-Partnership of this cohort",
            "–" if pd.isna(first_lp) else f"{first_lp:%d %b %Y}",
            "No limited partnerships"
            if pd.isna(first_lp)
            else f"{s.first_limited_partnership_name}, incorporated",
        ),
    ],
    columns=2,
)
if s.is_truncated:
    st.warning(
        f"The API reports {s.total_results:,} matches but only returns the first 1,000; "
        f"Q2 to Q6 cover the {s.results_fetched:,} fetched."
    )

q5_title = st.empty()  # filled once the input below is read, so the title shows its text
needle = st.text_input("Text the company name also contains", value="vate")
q5_title.subheader(f'Q5 - Companies with "{needle.upper()}" in title')
matches = companies[companies.company_name.str.contains(needle, case=False, regex=False)]
st.caption(f"{len(matches):,} companies")
table(matches[["company_number", "company_name", "company_status", "incorporated_on"]])

st.subheader("Q6 - Sum of premises digits by company type")
premises = query(
    "select * from analytics.search_premises_by_company_type where search_term = ?", term
)
st.altair_chart(
    bar_chart(premises, "company_type_description", "premises_number_sum"), width="stretch"
)

st.subheader("Explore Dataset")
st.caption("Each company with its latest person with significant control (blank if none)")
dataset = query(
    "select * from analytics.search_companies_with_pscs where search_term = ? order by search_rank",
    term,
)
table(dataset.drop(columns="search_term"))

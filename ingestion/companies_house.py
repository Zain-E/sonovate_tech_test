"""dlt source for the Companies House public data API (company search + PSCs)."""

import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

import dlt
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.auth import HttpBasicAuth
from dlt.sources.helpers.rest_client.exceptions import IgnoreResponseException
from dlt.sources.helpers.rest_client.paginators import OffsetPaginator
from requests import Response

BASE_URL = "https://api.company-information.service.gov.uk"
SEARCH_PATH = "/search/companies"
PSC_PATH = "/company/{company_number}/persons-with-significant-control"
PAGE_SIZE = 100  # the API silently caps items_per_page at 100
MAX_RESULTS = 1000  # the API errors once start_index goes beyond the first 1,000 results
RATE_LIMIT_HEADROOM = 10  # requests to leave unused in each 5-minute window
COMPANY_FIELDS = (
    "company_number",
    "title",
    "company_status",
    "company_type",
    "date_of_creation",
    "date_of_cessation",
    "address",
)


def make_client(api_key: str, base_url: str = BASE_URL) -> RESTClient:
    """Authenticated client that pages through search results up to the API's hard cap."""
    return RESTClient(
        base_url=base_url,
        auth=HttpBasicAuth(username=api_key, password=""),  # key is the username, no password
        paginator=OffsetPaginator(
            limit=PAGE_SIZE,
            offset_param="start_index",
            limit_param="items_per_page",
            total_path="total_results",
            maximum_offset=MAX_RESULTS,
        ),
        data_selector="items",
    )


def count_companies(client: RESTClient, term: str) -> dict:
    """The API's own match count, which can exceed what the 1,000-result cap lets us fetch."""
    response = client.get(SEARCH_PATH, params={"q": term, "items_per_page": 1})
    response.raise_for_status()
    return {
        "search_term": term,
        "total_results": response.json().get("total_results", 0),
        "searched_at": datetime.now(UTC),
    }


def search_companies(client: RESTClient, term: str) -> Iterator[dict]:
    """Every fetchable search result for `term`, tagged with the term and its rank."""
    searched_at = datetime.now(UTC)
    items = (item for page in client.paginate(SEARCH_PATH, params={"q": term}) for item in page)
    for rank, item in enumerate(items, start=1):
        yield {**item, "search_term": term, "search_rank": rank, "searched_at": searched_at}


def company_attributes(result: dict) -> dict:
    """A search result without what depends on the search (term, rank, highlighted matches), so a
    company found by several terms, or unchanged since the last run, is the same SCD2 version."""
    return {field: result.get(field) for field in COMPANY_FIELDS}


def wait_for_rate_limit(response: Response, *args, **kwargs) -> None:
    """Sleep until the window resets once the API says the quota (600 / 5 min) is nearly spent."""
    remaining = response.headers.get("X-Ratelimit-Remain")
    reset_at = response.headers.get("X-Ratelimit-Reset")  # epoch seconds
    if remaining is not None and reset_at is not None and int(remaining) <= RATE_LIMIT_HEADROOM:
        time.sleep(max(0.0, int(reset_at) - time.time()) + 1)


def skip_not_found(response: Response, *args, **kwargs) -> None:
    """Companies with no PSC record (e.g. dissolved before the 2016 register) return 404."""
    if response.status_code == 404:
        raise IgnoreResponseException
    response.raise_for_status()


def list_persons_with_significant_control(
    client: RESTClient, company_number: str
) -> Iterator[dict]:
    """Every PSC registered against a company, current and ceased, tagged with its company."""
    path = PSC_PATH.format(company_number=company_number)
    hooks = {"response": [wait_for_rate_limit, skip_not_found]}
    for page in client.paginate(path, hooks=hooks):
        for item in page:
            yield {**item, "company_number": company_number}


@dlt.source(name="companies_house", max_table_nesting=0)  # nested objects land as JSON
def companies_house(
    search_terms: Sequence[str] = dlt.config.value,
    api_key: str = dlt.secrets.value,
    base_url: str = BASE_URL,
):
    client = make_client(api_key, base_url)

    # Every run is a full extract. Search snapshots are appended; companies and PSCs are SCD2, so
    # dlt opens a new version when a record changes and closes the old one, or closes it when the
    # record is no longer returned.
    scd2 = {"disposition": "merge", "strategy": "scd2"}

    @dlt.resource(write_disposition="append")
    def company_searches() -> Iterator[dict]:
        for term in search_terms:
            yield count_companies(client, term)

    # Declared so the columns always exist (even with no dissolved companies) and land typed.
    date_columns = {c: {"data_type": "date"} for c in ("date_of_creation", "date_of_cessation")}

    @dlt.resource(write_disposition="append", columns=date_columns)
    def company_search_results() -> Iterator[dict]:
        for term in search_terms:
            yield from search_companies(client, term)

    seen_companies: set[str] = set()

    @dlt.transformer(
        data_from=company_search_results,
        write_disposition=scd2,
        columns={**date_columns, "address": {"data_type": "json"}},
    )
    def companies(result: dict) -> Iterator[dict]:
        # One record per company per run, even when several search terms (or pages) return it.
        if result["company_number"] not in seen_companies:
            seen_companies.add(result["company_number"])
            yield company_attributes(result)

    # Declared so staging can rely on them even when no PSC in the load has, say, identification.
    psc_columns = {
        **{c: {"data_type": "date"} for c in ("notified_on", "ceased_on")},
        **{c: {"data_type": "bool"} for c in ("ceased", "is_sanctioned")},
        **{
            c: {"data_type": "text"}
            for c in ("kind", "name", "nationality", "country_of_residence")
        },
        **{
            c: {"data_type": "json"}
            for c in (
                "address",
                "date_of_birth",
                "identification",
                "links",
                "name_elements",
                "natures_of_control",
            )
        },
    }

    @dlt.transformer(data_from=companies, write_disposition=scd2, columns=psc_columns)
    def persons_with_significant_control(company: dict) -> Iterator[dict]:
        yield from list_persons_with_significant_control(client, company["company_number"])

    return company_searches, company_search_results, companies, persons_with_significant_control

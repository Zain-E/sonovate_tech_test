-- One row per search term per run: the API's match count vs. how many we could actually fetch.
with fetched as (
    select load_id, search_term, count(*) as results_fetched
    from {{ ref('stg_companies_house__company_search_results') }}
    group by all
)

select
    searches.load_id,
    searches.loaded_at,
    searches.search_term,
    searches.total_results,
    coalesce(fetched.results_fetched, 0) as results_fetched,
    searches.total_results > coalesce(fetched.results_fetched, 0) as is_truncated,
    searches.searched_at,
    searches.loaded_at = max(searches.loaded_at) over () as is_latest_snapshot
from {{ ref('stg_companies_house__company_searches') }} as searches
left join fetched using (load_id, search_term)

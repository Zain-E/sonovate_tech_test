-- One row per search term: the API's match count vs. how many we could actually fetch.
with fetched as (
    select search_term, count(*) as results_fetched
    from {{ ref('fct_company_search_results') }}
    group by search_term
)

select
    searches.search_term,
    searches.total_results,
    coalesce(fetched.results_fetched, 0) as results_fetched,
    searches.total_results > coalesce(fetched.results_fetched, 0) as is_truncated,
    searches.searched_at
from {{ ref('stg_companies_house__company_searches') }} as searches
left join fetched using (search_term)

-- Which companies each search term returned, per run. Grain: run x search term x company.
select
    load_id,
    loaded_at,
    search_term,
    company_number,
    search_rank,
    searched_at,
    loaded_at = (
        select max(loaded_at) from {{ ref('stg_companies_house__company_searches') }}
    ) as is_latest_snapshot
from {{ ref('stg_companies_house__company_search_results') }}

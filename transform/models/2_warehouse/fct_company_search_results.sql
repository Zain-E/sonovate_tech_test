-- Which companies each search term returned. Grain: search term x company.
select
    search_term,
    company_number,
    search_rank,
    searched_at
from {{ ref('stg_companies_house__company_search_results') }}

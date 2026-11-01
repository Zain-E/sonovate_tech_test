-- Which companies each search returned, per pipeline run. Company attributes live in
-- stg_companies_house__companies, versioned.
select
    _dlt_load_id as load_id,
    to_timestamp(cast(_dlt_load_id as double)) as loaded_at,
    search_term,
    search_rank,
    company_number,
    searched_at
from {{ source('companies_house', 'company_search_results') }}
-- Offset pagination over a live index can return a company twice; keep its best rank.
qualify row_number() over (
    partition by _dlt_load_id, search_term, company_number order by search_rank
) = 1

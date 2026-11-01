-- One row per search term per pipeline run (snapshot).
select
    _dlt_load_id as load_id,
    to_timestamp(cast(_dlt_load_id as double)) as loaded_at,
    search_term,
    total_results,
    searched_at
from {{ source('companies_house', 'company_searches') }}

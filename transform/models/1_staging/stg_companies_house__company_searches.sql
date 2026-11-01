select
    search_term,
    total_results,
    searched_at
from {{ source('companies_house', 'company_searches') }}

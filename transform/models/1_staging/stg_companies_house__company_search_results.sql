select
    search_term,
    search_rank,
    company_number,
    title as company_name,
    company_status,
    company_type,
    cast(date_of_creation as date) as incorporated_on,
    cast(date_of_cessation as date) as ceased_on,
    address ->> 'premises' as address_premises,
    address ->> 'address_line_1' as address_line_1,
    address ->> 'address_line_2' as address_line_2,
    address ->> 'locality' as address_locality,
    address ->> 'region' as address_region,
    address ->> 'postal_code' as address_postal_code,
    address ->> 'country' as address_country,
    searched_at
from {{ source('companies_house', 'company_search_results') }}
-- Offset pagination over a live index can return a company twice; keep its best rank.
qualify row_number() over (partition by search_term, company_number order by search_rank) = 1

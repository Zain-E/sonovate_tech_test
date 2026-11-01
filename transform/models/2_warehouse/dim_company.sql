-- One row per company. A company found by several search terms keeps its latest-seen attributes.
with companies as (
    select *
    from {{ ref('stg_companies_house__company_search_results') }}
    qualify row_number() over (partition by company_number order by searched_at desc) = 1
)

select
    company_number,
    company_name,
    company_status,
    company_type,
    incorporated_on,
    ceased_on,
    date_diff('day', incorporated_on, ceased_on) as lifespan_days,
    address_premises,
    {{ digits_to_number('address_premises') }} as premises_number,
    address_line_1,
    address_line_2,
    address_locality,
    address_region,
    address_postal_code,
    address_country
from companies

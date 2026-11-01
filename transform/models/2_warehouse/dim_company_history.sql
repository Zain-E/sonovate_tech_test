-- Every version of every company returned by any search (SCD2). dim_company is the current one.
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
    address_country,
    valid_from,
    valid_to,
    is_current
from {{ ref('stg_companies_house__companies') }}

-- One row per version of a company (SCD2, maintained by dlt).
select
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
    _dlt_valid_from as valid_from,
    _dlt_valid_to as valid_to,
    _dlt_valid_to is null as is_current
from {{ source('companies_house', 'companies') }}

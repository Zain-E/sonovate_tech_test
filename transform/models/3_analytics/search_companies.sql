-- Every company each search term returned, with descriptive attributes. Grain: search term x company.
select
    results.search_term,
    results.search_rank,
    company.company_number,
    company.company_name,
    company.company_status,
    coalesce(status.company_status_description, company.company_status) as company_status_description,
    company.company_type,
    coalesce(type.company_type_description, company.company_type) as company_type_description,
    company.incorporated_on,
    company.ceased_on,
    company.lifespan_days,
    company.address_premises,
    company.premises_number,
    company.address_locality,
    company.address_postal_code
from {{ ref('fct_company_search_results') }} as results
inner join {{ ref('dim_company') }} as company using (company_number)
left join {{ ref('dim_company_type') }} as type using (company_type)
left join {{ ref('dim_company_status') }} as status using (company_status)

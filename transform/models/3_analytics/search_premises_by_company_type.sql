-- Sum of premises numbers by company type. Grain: search term x company type.
select
    search_term,
    company_type,
    company_type_description,
    count(*) as companies,
    count(premises_number) as companies_with_premises_number,
    coalesce(sum(premises_number), 0) as premises_number_sum
from {{ ref('search_companies') }}
group by all

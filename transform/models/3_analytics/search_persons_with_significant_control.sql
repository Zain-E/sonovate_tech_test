-- Persons with significant control of the companies each search term returned in the latest run,
-- current versions, including those whose control has ceased. Grain: search term x PSC.
select
    results.search_term,
    psc.company_number,
    company.company_name,
    psc.psc_id,
    psc.psc_kind,
    psc.psc_name,
    psc.nationality,
    psc.country_of_residence,
    psc.natures_of_control,
    psc.notified_on,
    psc.ceased_on,
    psc.is_ceased
from {{ ref('fct_company_search_results') }} as results
inner join {{ ref('dim_company') }} as company using (company_number)
inner join {{ ref('dim_person_with_significant_control') }} as psc using (company_number)
where results.is_latest_snapshot

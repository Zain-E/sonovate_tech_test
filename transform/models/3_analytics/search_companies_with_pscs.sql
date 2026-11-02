-- Every company each search term returned in the latest run, with its latest person with
-- significant control. Grain: search term x company. The latest PSC is the most recently notified
-- one that still has control, or, if all have ceased, the most recently notified overall. A company
-- with no PSC record has empty PSC columns.
with latest_pscs as (
    select *
    from {{ ref('search_persons_with_significant_control') }}
    qualify row_number() over (
        partition by search_term, company_number
        order by is_ceased, notified_on desc nulls last, psc_id
    ) = 1
)

select
    companies.*,
    pscs.psc_id,
    pscs.psc_kind,
    pscs.psc_name,
    pscs.nationality as psc_nationality,
    pscs.country_of_residence as psc_country_of_residence,
    pscs.natures_of_control as psc_natures_of_control,
    pscs.notified_on as psc_notified_on,
    pscs.ceased_on as psc_ceased_on,
    pscs.is_ceased as psc_is_ceased
from {{ ref('search_companies') }} as companies
left join latest_pscs as pscs using (search_term, company_number)

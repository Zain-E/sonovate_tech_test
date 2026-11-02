-- One row per PSC of a company in dim_company: its current version, whether or not it has ceased.
-- PSCs are only re-fetched for some companies each run, so a company that stopped being returned
-- keeps open PSC versions; the filter keeps this dim in step with dim_company.
select * exclude (valid_to, is_current)
from {{ ref('dim_person_with_significant_control_history') }}
where is_current
    and company_number in (select company_number from {{ ref('dim_company') }})

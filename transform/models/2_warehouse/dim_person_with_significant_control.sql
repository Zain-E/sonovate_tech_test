-- One row per PSC of a company in dim_company: its current version, whether or not it has ceased.
select * exclude (valid_to, is_current)
from {{ ref('dim_person_with_significant_control_history') }}
where is_current

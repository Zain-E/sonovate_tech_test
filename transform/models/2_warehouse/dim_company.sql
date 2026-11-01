-- One row per company: its current version. Companies the latest run did not return drop out.
select * exclude (valid_to, is_current)
from {{ ref('dim_company_history') }}
where is_current

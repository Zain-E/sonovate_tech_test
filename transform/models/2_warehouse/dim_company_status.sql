select
    company_status,
    description as company_status_description
from {{ ref('company_statuses') }}

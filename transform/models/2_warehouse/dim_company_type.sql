select
    company_type,
    description as company_type_description
from {{ ref('company_types') }}

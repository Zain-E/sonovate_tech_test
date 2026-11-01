-- Headline figures per search term from the latest run. Grain: search term.
with company_stats as (
    select
        search_term,
        count(*) filter (where company_status = 'active') as active_companies,
        count(*) filter (where company_status = 'dissolved') as dissolved_companies,
        avg(lifespan_days) filter (where company_status = 'dissolved') as avg_dissolved_lifespan_days,
        min(incorporated_on) filter (where company_type = 'limited-partnership')
            as first_limited_partnership_incorporated_on,
        arg_min(company_name, incorporated_on) filter (where company_type = 'limited-partnership')
            as first_limited_partnership_name
    from {{ ref('search_companies') }}
    group by search_term
)

select
    searches.search_term,
    searches.total_results,
    searches.results_fetched,
    searches.is_truncated,
    coalesce(company_stats.active_companies, 0) as active_companies,
    coalesce(company_stats.dissolved_companies, 0) as dissolved_companies,
    company_stats.avg_dissolved_lifespan_days,
    company_stats.first_limited_partnership_incorporated_on,
    company_stats.first_limited_partnership_name,
    searches.searched_at
from {{ ref('fct_company_searches') }} as searches
left join company_stats using (search_term)
where searches.is_latest_snapshot

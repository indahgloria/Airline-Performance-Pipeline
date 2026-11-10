-- Reconciliation: every month must have the same number of flights in the fact table as in
-- staging. Catches a broken incremental run (missed month, double-loaded month).
-- A dbt test passes when this returns zero rows.
with s as (select data_month, count(*) as n from {{ ref('stg_flights') }} group by 1),
     f as (select data_month, count(*) as n from {{ ref('fct_flights') }} group by 1)
select coalesce(s.data_month, f.data_month) as data_month, s.n as staging_rows, f.n as fact_rows
from s
full outer join f using (data_month)
where s.n is distinct from f.n

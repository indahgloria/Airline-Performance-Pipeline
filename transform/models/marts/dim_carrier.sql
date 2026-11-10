-- Every carrier that appears in the data, named from the reference seed.
-- A carrier BTS adds later still shows up (as "Unknown (XX)") instead of disappearing from joins.
with observed as (
    select distinct carrier_code from {{ ref('stg_flights') }}
)
select
    o.carrier_code,
    coalesce(s.carrier_name, 'Unknown (' || o.carrier_code || ')') as carrier_name,
    coalesce(s.carrier_type, 'unknown')                           as carrier_type,
    s.carrier_code is not null                                    as is_in_reference
from observed o
left join {{ ref('carriers') }} s using (carrier_code)

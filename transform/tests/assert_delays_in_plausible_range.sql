{{ config(severity='warn') }}
-- Real BTS data does contain extreme delays (20+ hours happens), so this only warns.
-- A flood of these would point at a parsing bug (e.g. HHMM read as minutes).
select flight_id, dep_delay_min, arr_delay_min
from {{ ref('fct_flights') }}
where dep_delay_min not between -90 and 2000
   or arr_delay_min not between -120 and 2000

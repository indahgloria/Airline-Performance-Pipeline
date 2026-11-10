-- Airports built from the data itself (BTS ships city/state on every row), latest name wins.
with both_sides as (
    select origin_airport as airport_code, origin_city_name as city_name, origin_state as state, flight_date
    from {{ ref('stg_flights') }}
    union all
    select dest_airport, dest_city_name, dest_state, flight_date
    from {{ ref('stg_flights') }}
)
select distinct on (airport_code)
    airport_code,
    city_name,
    state
from both_sides
order by airport_code, flight_date desc

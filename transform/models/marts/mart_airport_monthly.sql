-- Departure performance by origin airport. Taxi-out time is a proxy for ground congestion.
with f as (
    select * from {{ ref('fct_flights') }}
)
select
    f.data_month,
    f.origin_airport                                                        as airport_code,
    a.city_name,
    count(*)                                                                as departures,
    round(avg(dep_delay_min) filter (where not is_cancelled), 1)            as avg_dep_delay_min,
    round(avg((dep_delay_min < 15)::int) filter (where not is_cancelled), 4) as on_time_departure_rate,
    round(avg(taxi_out_min), 1)                                             as avg_taxi_out_min,
    round(avg(is_cancelled::int), 4)                                        as cancellation_rate
from f
join {{ ref('dim_airport') }} a on a.airport_code = f.origin_airport
group by 1, 2, 3

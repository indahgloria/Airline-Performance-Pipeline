-- How performance decays through the day (scheduled departure hour, local time).
-- The "late aircraft" share shows delays snowballing: one late plane makes its next flights late.
with f as (
    select * from {{ ref('fct_flights') }}
)
select
    data_month,
    crs_dep_hour,
    count(*)                                                                as flights,
    round(avg(is_on_time::int) filter (where not is_cancelled), 4)          as on_time_rate,
    round(avg(arr_delay_min) filter (where not is_cancelled and not is_diverted), 1) as avg_arr_delay_min,
    round(
        sum(late_aircraft_delay_min) * 1.0 / nullif(sum(
            coalesce(carrier_delay_min, 0) + coalesce(weather_delay_min, 0) + coalesce(nas_delay_min, 0)
            + coalesce(security_delay_min, 0) + coalesce(late_aircraft_delay_min, 0)), 0), 4
    )                                                                       as late_aircraft_share
from f
group by 1, 2

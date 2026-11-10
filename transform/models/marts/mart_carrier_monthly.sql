-- Carrier scorecard per month: the question an ops team asks first ("who's on time?").
with f as (
    select * from {{ ref('fct_flights') }}
)
select
    f.data_month,
    f.carrier_code,
    c.carrier_name,
    c.carrier_type,
    count(*)                                                                as scheduled_flights,
    count(*) filter (where is_cancelled)                                    as cancelled_flights,
    round(avg(is_cancelled::int), 4)                                        as cancellation_rate,
    round(avg(is_on_time::int) filter (where not is_cancelled), 4)          as on_time_rate,
    round(avg(arr_delay_min) filter (where not is_cancelled and not is_diverted), 1) as avg_arr_delay_min,
    percentile_cont(0.9) within group (order by arr_delay_min)
        filter (where not is_cancelled and not is_diverted)                 as p90_arr_delay_min,
    rank() over (
        partition by f.data_month
        order by avg(is_on_time::int) filter (where not is_cancelled) desc
    )                                                                       as on_time_rank
from f
join {{ ref('dim_carrier') }} c using (carrier_code)
group by 1, 2, 3, 4

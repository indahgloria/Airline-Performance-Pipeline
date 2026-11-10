-- Where do delay minutes come from? BTS attributes every 15+ min arrival delay to 5 causes.
-- Unpivoted (one row per cause) so it charts and filters easily.
with f as (
    select * from {{ ref('fct_flights') }} where is_arr_delayed_15
),
unpivoted as (
    select data_month, carrier_code, 'Carrier'        as cause, carrier_delay_min       as minutes from f
    union all select data_month, carrier_code, 'Weather',        weather_delay_min       from f
    union all select data_month, carrier_code, 'Air traffic (NAS)', nas_delay_min        from f
    union all select data_month, carrier_code, 'Security',       security_delay_min      from f
    union all select data_month, carrier_code, 'Late aircraft',  late_aircraft_delay_min from f
)
select
    data_month,
    carrier_code,
    cause,
    sum(minutes)                                                            as delay_minutes,
    round(sum(minutes) * 1.0 / nullif(sum(sum(minutes)) over (partition by data_month, carrier_code), 0), 4)
                                                                            as share_of_carrier_delay
from unpivoted
group by 1, 2, 3

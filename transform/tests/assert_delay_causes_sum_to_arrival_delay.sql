-- BTS business rule: for 15+ minute arrival delays, the five cause columns add up to ArrDelay.
-- If they don't, either the source changed or our casting/rounding is wrong.
select flight_id, arr_delay_min,
       carrier_delay_min + weather_delay_min + nas_delay_min + security_delay_min + late_aircraft_delay_min as cause_total
from {{ ref('fct_flights') }}
where is_arr_delayed_15
  and carrier_delay_min is not null
  and abs(arr_delay_min - (carrier_delay_min + weather_delay_min + nas_delay_min
                           + security_delay_min + late_aircraft_delay_min)) > 1

-- One clean, typed row per flight.
--   * text -> proper types
--   * HHMM clock strings -> minutes after midnight
--   * duplicate submissions removed (same flight reported twice)
--   * a stable surrogate key, flight_id, so downstream joins/tests have a real primary key

with source as (
    select * from {{ source('raw', 'flights') }}
),

typed as (
    select
        data_month,
        _file_name,
        _loaded_at,
        flight_date::date                                        as flight_date,
        reporting_airline                                        as carrier_code,
        tail_number,
        flight_number::int                                       as flight_number,
        origin                                                   as origin_airport,
        origin_city_name,
        origin_state,
        dest                                                     as dest_airport,
        dest_city_name,
        dest_state,
        {{ hhmm_to_minutes('crs_dep_time') }}                    as crs_dep_minute,
        {{ hhmm_to_minutes('dep_time') }}                        as dep_minute,
        {{ hhmm_to_minutes('crs_arr_time') }}                    as crs_arr_minute,
        {{ hhmm_to_minutes('arr_time') }}                        as arr_minute,
        {{ to_num('dep_delay') }}::int                           as dep_delay_min,
        {{ to_num('arr_delay') }}::int                           as arr_delay_min,
        {{ to_num('taxi_out') }}::int                            as taxi_out_min,
        {{ to_num('taxi_in') }}::int                             as taxi_in_min,
        {{ to_num('crs_elapsed_time') }}::int                    as crs_elapsed_min,
        {{ to_num('actual_elapsed_time') }}::int                 as actual_elapsed_min,
        {{ to_num('air_time') }}::int                            as air_time_min,
        {{ to_num('distance') }}::int                            as distance_miles,
        coalesce({{ to_num('cancelled') }}, 0) = 1               as is_cancelled,
        cancellation_code,
        coalesce({{ to_num('diverted') }}, 0) = 1                as is_diverted,
        {{ to_num('carrier_delay') }}::int                       as carrier_delay_min,
        {{ to_num('weather_delay') }}::int                       as weather_delay_min,
        {{ to_num('nas_delay') }}::int                           as nas_delay_min,
        {{ to_num('security_delay') }}::int                      as security_delay_min,
        {{ to_num('late_aircraft_delay') }}::int                 as late_aircraft_delay_min,
        crs_dep_time                                             as crs_dep_time_raw
    from source
),

deduped as (
    select
        *,
        row_number() over (
            partition by flight_date, carrier_code, flight_number, origin_airport, dest_airport, crs_dep_time_raw
            order by _loaded_at desc
        ) as _rn
    from typed
)

select
    md5(concat_ws('|', flight_date, carrier_code, flight_number, origin_airport, dest_airport, crs_dep_time_raw)) as flight_id,
    data_month, _file_name, _loaded_at,
    flight_date, carrier_code, tail_number, flight_number,
    origin_airport, origin_city_name, origin_state,
    dest_airport, dest_city_name, dest_state,
    crs_dep_minute, crs_dep_minute / 60                         as crs_dep_hour,
    dep_minute, crs_arr_minute, arr_minute,
    dep_delay_min, arr_delay_min, taxi_out_min, taxi_in_min,
    crs_elapsed_min, actual_elapsed_min, air_time_min, distance_miles,
    is_cancelled, cancellation_code, is_diverted,
    carrier_delay_min, weather_delay_min, nas_delay_min, security_delay_min, late_aircraft_delay_min
from deduped
where _rn = 1

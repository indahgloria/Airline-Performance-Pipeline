{#
  Incremental fact table. Grain: one row per flight.

  First run: builds everything.
  Later runs: only rebuilds the month(s) that were (re)loaded since the last run.
    - finds months in staging with _loaded_at newer than anything already in this table
    - delete+insert keyed on data_month = the whole month is swapped, so a corrected
      re-download of a month replaces it cleanly (no stale or duplicate rows left behind)
  With 12+ months of ~550K rows each, this turns a full rebuild into a one-month rebuild.
#}
{{
  config(
    materialized='incremental',
    unique_key='data_month',
    incremental_strategy='delete+insert',
    on_schema_change='append_new_columns',
    indexes=[
      {'columns': ['flight_id'], 'unique': True},
      {'columns': ['flight_date']},
      {'columns': ['carrier_code', 'data_month']},
    ]
  )
}}

select
    flight_id,
    data_month,
    flight_date,
    extract(isodow from flight_date)::int                         as day_of_week,
    carrier_code,
    tail_number,
    flight_number,
    origin_airport,
    dest_airport,
    crs_dep_minute,
    crs_dep_hour,
    dep_delay_min,
    arr_delay_min,
    taxi_out_min,
    taxi_in_min,
    air_time_min,
    distance_miles,
    is_cancelled,
    cancellation_code,
    is_diverted,
    -- DOT definition: on time = arrived < 15 min after schedule. Cancelled/diverted are not on time.
    (not is_cancelled and not is_diverted and arr_delay_min < 15)   as is_on_time,
    (arr_delay_min >= 15)                                           as is_arr_delayed_15,
    carrier_delay_min,
    weather_delay_min,
    nas_delay_min,
    security_delay_min,
    late_aircraft_delay_min,
    _loaded_at
from {{ ref('stg_flights') }}

{% if is_incremental() %}
where data_month in (
    select distinct data_month
    from {{ ref('stg_flights') }}
    where _loaded_at > (select coalesce(max(_loaded_at), '1900-01-01'::timestamptz) from {{ this }})
)
{% endif %}

-- Every flight must sit in the partition for its own month.
select flight_id, flight_date, data_month
from {{ ref('fct_flights') }}
where date_trunc('month', flight_date)::date <> data_month

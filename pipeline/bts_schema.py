"""The data contract with the source.

BTS files have 110 columns (plus an empty trailing one — the 'Unnamed: 109' you saw in pandas).
We only depend on the columns below. If BTS ever renames or drops one of these, ingestion
fails loudly *before* touching the database instead of silently loading NULLs.
"""

# BTS header name  ->  column name in raw.flights
REQUIRED_COLUMNS = {
    "FlightDate": "flight_date",
    "Reporting_Airline": "reporting_airline",
    "Tail_Number": "tail_number",
    "Flight_Number_Reporting_Airline": "flight_number",
    "Origin": "origin",
    "OriginCityName": "origin_city_name",
    "OriginState": "origin_state",
    "Dest": "dest",
    "DestCityName": "dest_city_name",
    "DestState": "dest_state",
    "CRSDepTime": "crs_dep_time",
    "DepTime": "dep_time",
    "DepDelay": "dep_delay",
    "TaxiOut": "taxi_out",
    "TaxiIn": "taxi_in",
    "CRSArrTime": "crs_arr_time",
    "ArrTime": "arr_time",
    "ArrDelay": "arr_delay",
    "Cancelled": "cancelled",
    "CancellationCode": "cancellation_code",
    "Diverted": "diverted",
    "CRSElapsedTime": "crs_elapsed_time",
    "ActualElapsedTime": "actual_elapsed_time",
    "AirTime": "air_time",
    "Distance": "distance",
    "CarrierDelay": "carrier_delay",
    "WeatherDelay": "weather_delay",
    "NASDelay": "nas_delay",
    "SecurityDelay": "security_delay",
    "LateAircraftDelay": "late_aircraft_delay",
}

-- Run once (safe to re-run). Creates the landing zone and the pipeline's own metadata.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS meta;

-- Landing table: exactly what the file said, as text. Typing happens in dbt (staging),
-- so a weird value never makes the load fail halfway and we can always re-derive from raw.
-- Partitioned by month: reloading a month = swap one partition, not rescan the whole table.
CREATE TABLE IF NOT EXISTS raw.flights (
    data_month          date        NOT NULL,
    _file_name          text        NOT NULL,
    _loaded_at          timestamptz NOT NULL DEFAULT now(),
    flight_date         text,
    reporting_airline   text,
    tail_number         text,
    flight_number       text,
    origin              text,
    origin_city_name    text,
    origin_state        text,
    dest                text,
    dest_city_name      text,
    dest_state          text,
    crs_dep_time        text,
    dep_time            text,
    dep_delay           text,
    taxi_out            text,
    taxi_in             text,
    crs_arr_time        text,
    arr_time            text,
    arr_delay           text,
    cancelled           text,
    cancellation_code   text,
    diverted            text,
    crs_elapsed_time    text,
    actual_elapsed_time text,
    air_time            text,
    distance            text,
    carrier_delay       text,
    weather_delay       text,
    nas_delay           text,
    security_delay      text,
    late_aircraft_delay text
) PARTITION BY RANGE (data_month);

-- One row per load attempt: what was loaded, when, how many rows, how long it took.
-- This is what makes the pipeline idempotent (skip files we've already loaded)
-- and observable (you can answer "when was March loaded and how long did it take?").
CREATE TABLE IF NOT EXISTS meta.ingestion_log (
    id              bigserial   PRIMARY KEY,
    file_name       text        NOT NULL,
    file_sha256     text        NOT NULL,
    data_month      date,
    rows_in_file    bigint,
    rows_loaded     bigint,
    extra_columns   int,
    status          text        NOT NULL,          -- success | failed
    error           text,
    started_at      timestamptz NOT NULL,
    finished_at     timestamptz,
    duration_sec    numeric(10, 2)
);
CREATE INDEX IF NOT EXISTS ix_ingestion_log_sha ON meta.ingestion_log (file_sha256, status);

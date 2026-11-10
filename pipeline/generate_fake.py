"""Generate fake monthly BTS files that look exactly like the real downloads.

Same zip name, same CSV name inside, same column headers, same quirks:
  * trailing empty column (the 'Unnamed: 109' problem)
  * times as HHMM strings, with '2400' for midnight
  * delay-cause columns only filled when ArrDelay >= 15 (and they sum to ArrDelay)
  * blanks for cancelled / diverted flights
Plus a little extra mess (duplicate rows, blank tail numbers) so the pipeline has real cleaning to do.

The real files have 110 columns; we write the ones the pipeline needs plus a few extras,
which also proves ingestion ignores columns it doesn't depend on.
"""
import calendar
import csv
import io
import math
import random
import zipfile
from datetime import date
from pathlib import Path

from .config import BTS_CSV_NAME, BTS_ZIP_NAME, RAW_DIR

# code, name, market-share weight, delay propensity (+ = more delays)
CARRIERS = [
    ("WN", 19, 0.02), ("DL", 16, -0.05), ("AA", 15, 0.04), ("OO", 12, 0.00), ("UA", 12, 0.02),
    ("YX", 5, -0.03), ("MQ", 4, 0.03), ("B6", 4, 0.08), ("AS", 4, -0.02), ("NK", 4, 0.06),
    ("9E", 4, -0.01), ("OH", 3, 0.01), ("F9", 3, 0.09), ("G4", 2, 0.07), ("HA", 1, -0.06),
]

# code, "City, ST", state, lat, lon, traffic weight, congestion (+ = slower taxi / more delays)
AIRPORTS = [
    ("ATL", "Atlanta, GA", "GA", 33.64, -84.43, 10, 0.03), ("DFW", "Dallas/Fort Worth, TX", "TX", 32.90, -97.04, 9, 0.03),
    ("DEN", "Denver, CO", "CO", 39.86, -104.67, 9, 0.04), ("ORD", "Chicago, IL", "IL", 41.98, -87.90, 9, 0.07),
    ("LAX", "Los Angeles, CA", "CA", 33.94, -118.41, 7, 0.03), ("CLT", "Charlotte, NC", "NC", 35.21, -80.94, 7, 0.02),
    ("LAS", "Las Vegas, NV", "NV", 36.08, -115.15, 6, 0.01), ("PHX", "Phoenix, AZ", "AZ", 33.43, -112.01, 5, 0.00),
    ("MCO", "Orlando, FL", "FL", 28.43, -81.31, 5, 0.04), ("SEA", "Seattle, WA", "WA", 47.45, -122.31, 5, 0.01),
    ("MIA", "Miami, FL", "FL", 25.79, -80.29, 4, 0.04), ("IAH", "Houston, TX", "TX", 29.98, -95.34, 4, 0.02),
    ("JFK", "New York, NY", "NY", 40.64, -73.78, 4, 0.08), ("EWR", "Newark, NJ", "NJ", 40.69, -74.17, 4, 0.10),
    ("SFO", "San Francisco, CA", "CA", 37.62, -122.38, 4, 0.06), ("BOS", "Boston, MA", "MA", 42.36, -71.01, 4, 0.05),
    ("MSP", "Minneapolis, MN", "MN", 44.88, -93.22, 4, 0.01), ("DTW", "Detroit, MI", "MI", 42.21, -83.35, 4, 0.01),
    ("LGA", "New York, NY", "NY", 40.78, -73.87, 4, 0.08), ("PHL", "Philadelphia, PA", "PA", 39.87, -75.24, 3, 0.04),
    ("SLC", "Salt Lake City, UT", "UT", 40.79, -111.98, 3, -0.01), ("BWI", "Baltimore, MD", "MD", 39.18, -76.67, 3, 0.01),
    ("DCA", "Washington, DC", "VA", 38.85, -77.04, 3, 0.03), ("SAN", "San Diego, CA", "CA", 32.73, -117.19, 2, 0.00),
    ("BNA", "Nashville, TN", "TN", 36.12, -86.68, 2, 0.01), ("AUS", "Austin, TX", "TX", 30.19, -97.67, 2, 0.01),
    ("HNL", "Honolulu, HI", "HI", 21.32, -157.92, 1, -0.03),
]

HEADER = [
    "Year", "Quarter", "Month", "DayofMonth", "DayOfWeek", "FlightDate", "Reporting_Airline",
    "DOT_ID_Reporting_Airline", "IATA_CODE_Reporting_Airline", "Tail_Number", "Flight_Number_Reporting_Airline",
    "Origin", "OriginCityName", "OriginState", "Dest", "DestCityName", "DestState",
    "CRSDepTime", "DepTime", "DepDelay", "DepDelayMinutes", "DepDel15", "DepTimeBlk", "TaxiOut",
    "TaxiIn", "CRSArrTime", "ArrTime", "ArrDelay", "ArrDelayMinutes", "ArrDel15", "ArrTimeBlk",
    "Cancelled", "CancellationCode", "Diverted", "CRSElapsedTime", "ActualElapsedTime", "AirTime",
    "Flights", "Distance", "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
    "",  # <- the trailing empty column real BTS files have
]

# share of scheduled departures by hour of day (06:00 - 22:00), roughly like real US schedules
HOUR_WEIGHTS = {6: 9, 7: 9, 8: 8, 9: 7, 10: 7, 11: 7, 12: 7, 13: 7, 14: 7, 15: 7, 16: 7, 17: 7, 18: 7, 19: 6, 20: 5, 21: 4, 22: 2}


def _miles(a, b) -> int:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[3], a[4], b[3], b[4]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return int(3959 * 2 * math.asin(math.sqrt(h)))


def _hhmm(minute_of_day: int, midnight_as_2400: bool = True) -> str:
    m = minute_of_day % 1440
    if m == 0 and midnight_as_2400:
        return "2400"
    return f"{m // 60:02d}{m % 60:02d}"


def _blk(minute_of_day: int) -> str:
    h = (minute_of_day % 1440) // 60
    return "0001-0559" if h < 6 else f"{h:02d}00-{h:02d}59"


def _split(total: int, weights: dict) -> dict:
    """Split `total` delay minutes across causes so the parts sum exactly to total."""
    s = sum(weights.values())
    raw = {k: total * w / s for k, w in weights.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: total - sum(out.values())]:
        out[k] += 1
    return out


def _f(x) -> str:
    return "" if x is None else f"{x:.2f}"


def generate_month(year: int, month: int, rows: int = 60_000, seed: int | None = None) -> Path:
    rng = random.Random(seed if seed is not None else year * 100 + month)
    days = calendar.monthrange(year, month)[1]
    winter = month in (12, 1, 2)
    storm_days = {rng.randint(1, days): rng.sample(range(len(AIRPORTS)), 6) for _ in range(4 if winter else 2)}
    holiday_days = {d for d in range(1, days + 1) if month == 12 and d >= 20}

    car_codes = [c[0] for c in CARRIERS]
    car_w = [c[1] for c in CARRIERS]
    car_adj = {c[0]: c[2] for c in CARRIERS}
    ap_w = [a[5] for a in AIRPORTS]
    hours, hour_w = list(HOUR_WEIGHTS), list(HOUR_WEIGHTS.values())
    tails = {c: [f"N{rng.randint(100, 999)}{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{c[0]}" for _ in range(220)] for c in car_codes}

    out_rows = []
    for _ in range(rows):
        carrier = rng.choices(car_codes, car_w)[0]
        oi, di = rng.choices(range(len(AIRPORTS)), ap_w, k=2)
        while di == oi:
            di = rng.choices(range(len(AIRPORTS)), ap_w)[0]
        o, d = AIRPORTS[oi], AIRPORTS[di]
        day = rng.randint(1, days)
        fdate = date(year, month, day)
        crs_dep = rng.choices(hours, hour_w)[0] * 60 + rng.choice(range(0, 60, 5))
        dist = _miles(o, d)
        crs_elapsed = int(dist / 7.8 + 32 + rng.randint(-4, 6))
        crs_arr = crs_dep + crs_elapsed + int((d[4] - o[4]) / 15 * 60)  # crude timezone shift

        storm = oi in storm_days.get(day, []) or di in storm_days.get(day, [])
        hour = crs_dep // 60
        p_delay = 0.10 + car_adj[carrier] + 0.011 * (hour - 6) + o[6] + 0.5 * d[6] + (0.35 if storm else 0) + (0.06 if day in holiday_days else 0)

        cancelled = rng.random() < (0.011 + (0.12 if storm else 0) + max(car_adj[carrier], 0) * 0.08)
        diverted = (not cancelled) and rng.random() < 0.0025
        taxi_out = max(5, int(rng.gauss(16 + 60 * o[6] + (10 if storm else 0), 5)))
        taxi_in = max(2, int(rng.gauss(8 + 30 * d[6], 3)))

        r = dict.fromkeys(HEADER, "")
        r.update({
            "Year": year, "Quarter": (month - 1) // 3 + 1, "Month": month, "DayofMonth": day,
            "DayOfWeek": fdate.isoweekday(), "FlightDate": fdate.isoformat(), "Reporting_Airline": carrier,
            "DOT_ID_Reporting_Airline": 19000 + car_codes.index(carrier), "IATA_CODE_Reporting_Airline": carrier,
            "Tail_Number": rng.choice(tails[carrier]) if rng.random() > 0.003 else "",
            "Flight_Number_Reporting_Airline": rng.randint(1, 6999),
            "Origin": o[0], "OriginCityName": o[1], "OriginState": o[2],
            "Dest": d[0], "DestCityName": d[1], "DestState": d[2],
            "CRSDepTime": _hhmm(crs_dep, False), "DepTimeBlk": _blk(crs_dep),
            "CRSArrTime": _hhmm(crs_arr), "ArrTimeBlk": _blk(crs_arr),
            "Cancelled": "1.00" if cancelled else "0.00", "Diverted": "1.00" if diverted else "0.00",
            "CRSElapsedTime": _f(crs_elapsed), "Flights": "1.00", "Distance": _f(dist),
        })

        if cancelled:
            r["CancellationCode"] = "B" if storm and rng.random() < 0.85 else rng.choices("ACBD", [50, 40, 10, 0.2])[0]
            out_rows.append(r)
            continue

        if rng.random() < p_delay:
            dep_delay = int(rng.expovariate(1 / (55 if storm else 38))) + 6
        else:
            dep_delay = rng.randint(-12, 5)
        r.update({
            "DepTime": _hhmm(crs_dep + dep_delay), "DepDelay": _f(dep_delay), "DepDelayMinutes": _f(max(dep_delay, 0)),
            "DepDel15": _f(1 if dep_delay >= 15 else 0), "TaxiOut": _f(taxi_out),
        })
        if diverted:
            out_rows.append(r)
            continue

        arr_delay = dep_delay + (taxi_out - 16) + rng.randint(-14, 6)
        air_time = crs_elapsed - taxi_out - taxi_in + rng.randint(-6, 6)
        r.update({
            "TaxiIn": _f(taxi_in), "ArrTime": _hhmm(crs_arr + arr_delay), "ArrDelay": _f(arr_delay),
            "ArrDelayMinutes": _f(max(arr_delay, 0)), "ArrDel15": _f(1 if arr_delay >= 15 else 0),
            "ActualElapsedTime": _f(crs_elapsed + arr_delay - dep_delay), "AirTime": _f(air_time),
        })
        if arr_delay >= 15:  # BTS only attributes causes for 15+ minute arrival delays
            causes = _split(arr_delay, {
                "CarrierDelay": 0.30 + 2 * max(car_adj[carrier], 0),
                "WeatherDelay": 0.55 if storm else 0.03,
                "NASDelay": 0.18 + 2 * max(o[6], d[6]),
                "SecurityDelay": 0.003,
                "LateAircraftDelay": 0.08 + 0.05 * (hour - 6),  # delays snowball through the day
            })
            r.update({k: _f(v) for k, v in causes.items()})
        out_rows.append(r)

    out_rows += [dict(x) for x in rng.sample(out_rows, max(1, rows // 2000))]  # duplicate submissions
    out_rows.sort(key=lambda x: (x["FlightDate"], x["Reporting_Airline"]))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zpath = RAW_DIR / BTS_ZIP_NAME.format(year=year, month=month)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEADER, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writeheader()
    w.writerows(out_rows)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(BTS_CSV_NAME.format(year=year, month=month), buf.getvalue())
    return zpath

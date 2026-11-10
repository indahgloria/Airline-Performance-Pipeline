"""Load monthly BTS files into raw.flights.

Design (each point is an interview talking point):
  1. Idempotent   - a file is identified by its SHA-256. Same file twice = skipped. Re-running
                    the whole pipeline is always safe.
  2. Atomic       - a month is replaced inside ONE transaction (truncate partition + insert).
                    If anything fails, the old data stays; nobody ever sees half a month.
  3. Fast         - Postgres COPY streamed straight from the zip, no pandas, constant memory.
                    (row-by-row INSERTs were the slow-pipeline problem; COPY is ~50-100x faster)
  4. Contract     - required columns are checked before loading. Renamed column = loud failure,
                    not a silent column of NULLs.
  5. Reconciled   - rows in file must equal rows landed, every rows' date must match the month.
  6. Observable   - every attempt (success or failure) is written to meta.ingestion_log.
"""
import csv
import hashlib
import io
import time
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from psycopg import sql

from .bts_schema import REQUIRED_COLUMNS
from .db import connect


class ContractError(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def open_csv(path: Path):
    """Return a binary stream of the CSV, whether the file is a .zip or a plain .csv."""
    if path.suffix == ".zip":
        z = zipfile.ZipFile(path)
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        return z.open(name)
    return open(path, "rb")


def landing_columns(header: list[str]) -> list[str]:
    """Make every header a valid, unique column name. The empty trailing column becomes _extra_N."""
    cols, seen = [], set()
    for i, h in enumerate(header):
        c = h.strip() or f"_extra_{i}"
        while c in seen:
            c += "_dup"
        seen.add(c)
        cols.append(c)
    return cols


def ingest_file(path: Path, force: bool = False) -> dict:
    digest = sha256(path)
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    with connect() as con:
        if not force:
            done = con.execute(
                "SELECT data_month, rows_loaded FROM meta.ingestion_log WHERE file_sha256 = %s AND status = 'success' LIMIT 1",
                (digest,),
            ).fetchone()
            if done:
                print(f"  skip   {path.name}  (already loaded: {done[0]:%Y-%m}, {done[1]:,} rows)")
                return {"file": path.name, "status": "skipped"}

        try:
            with open_csv(path) as f:
                header = next(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")))
            missing = [c for c in REQUIRED_COLUMNS if c not in header]
            if missing:
                raise ContractError(f"{path.name} is missing required columns: {missing}")
            cols = landing_columns(header)
            extra = len([h for h in header if h and h not in REQUIRED_COLUMNS])

            with con.transaction():
                # 1. land the whole file into a temp table (all text, all columns) with COPY
                con.execute(
                    sql.SQL("CREATE TEMP TABLE _landing ({}) ON COMMIT DROP").format(
                        sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in cols)
                    )
                )
                with con.cursor() as cur, cur.copy("COPY _landing FROM STDIN (FORMAT csv, HEADER true)") as cp, open_csv(path) as f:
                    while chunk := f.read(1 << 20):
                        cp.write(chunk)
                rows_in_file = con.execute("SELECT count(*) FROM _landing").fetchone()[0]

                # 2. which month is this? every row must belong to the same one
                months = con.execute(
                    'SELECT DISTINCT date_trunc(\'month\', "FlightDate"::date)::date FROM _landing'
                ).fetchall()
                if len(months) != 1:
                    raise ContractError(f"{path.name} spans {len(months)} months, expected exactly 1")
                month: date = months[0][0]
                part = f"flights_{month:%Y_%m}"
                nxt = date(month.year + month.month // 12, month.month % 12 + 1, 1)

                # 3. atomic replace of that month's partition
                con.execute(
                    sql.SQL("CREATE TABLE IF NOT EXISTS raw.{} PARTITION OF raw.flights FOR VALUES FROM ({}) TO ({})").format(
                        sql.Identifier(part), sql.Literal(month), sql.Literal(nxt)
                    )
                )
                con.execute(sql.SQL("TRUNCATE raw.{}").format(sql.Identifier(part)))
                targets = list(REQUIRED_COLUMNS.values())
                sources = list(REQUIRED_COLUMNS.keys())
                inserted = con.execute(
                    sql.SQL("INSERT INTO raw.flights (data_month, _file_name, {}) SELECT %s, %s, {} FROM _landing").format(
                        sql.SQL(", ").join(map(sql.Identifier, targets)),
                        sql.SQL(", ").join(sql.SQL("NULLIF({}, '')").format(sql.Identifier(s)) for s in sources),
                    ),
                    (month, path.name),
                ).rowcount

                # 4. reconcile
                if inserted != rows_in_file:
                    raise ContractError(f"row count mismatch: file={rows_in_file} loaded={inserted}")

                dur = time.perf_counter() - t0
                con.execute(
                    """INSERT INTO meta.ingestion_log
                       (file_name, file_sha256, data_month, rows_in_file, rows_loaded, extra_columns,
                        status, started_at, finished_at, duration_sec)
                       VALUES (%s,%s,%s,%s,%s,%s,'success',%s,now(),%s)""",
                    (path.name, digest, month, rows_in_file, inserted, extra, started, round(dur, 2)),
                )
            print(f"  load   {path.name}  -> raw.{part}: {inserted:,} rows in {dur:.1f}s ({inserted / dur:,.0f} rows/s)")
            return {"file": path.name, "status": "success", "month": month, "rows": inserted}

        except Exception as e:
            con.rollback()
            con.execute(
                """INSERT INTO meta.ingestion_log (file_name, file_sha256, status, error, started_at, finished_at, duration_sec)
                   VALUES (%s,%s,'failed',%s,%s,now(),%s)""",
                (path.name, digest, str(e)[:2000], started, round(time.perf_counter() - t0, 2)),
            )
            con.commit()
            print(f"  FAIL   {path.name}: {e}")
            raise

"""Command line entry point.

    python -m pipeline run --source fake --months 2025-01:2025-03     # whole pipeline, fake data
    python -m pipeline run --source real --months 2025-01:2025-03     # whole pipeline, real BTS data
    python -m pipeline ingest                                         # load whatever is in data/raw
    python -m pipeline transform                                      # dbt build only
    python -m pipeline report                                         # rebuild reports/flight_delays.html
    python -m pipeline status                                         # what's been loaded
"""
import argparse
import time

from .config import BTS_ZIP_NAME, RAW_DIR


def parse_months(spec: str) -> list[tuple[int, int]]:
    """'2025-01:2025-03' -> [(2025,1),(2025,2),(2025,3)];  '2025-01,2025-06' -> two months."""
    out = []
    for part in spec.split(","):
        a, _, b = part.partition(":")
        y, m = map(int, a.split("-"))
        y2, m2 = map(int, (b or a).split("-"))
        while (y, m) <= (y2, m2):
            out.append((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def cmd_get(source: str, months, rows: int) -> list:
    paths = []
    for y, m in months:
        if source == "fake":
            from .generate_fake import generate_month
            p = RAW_DIR / BTS_ZIP_NAME.format(year=y, month=m)
            if p.exists():
                print(f"  keep   {p.name} (already generated)")
            else:
                p = generate_month(y, m, rows=rows)
                print(f"  gen    {p.name}")
        else:
            from .download import download_month
            p = download_month(y, m)
        paths.append(p)
    return paths


def cmd_ingest(paths=None, force=False) -> None:
    from .db import bootstrap
    from .ingest import ingest_file
    bootstrap()
    paths = paths or sorted(list(RAW_DIR.glob("*.zip")) + list(RAW_DIR.glob("*.csv")))
    if not paths:
        print(f"  nothing to ingest in {RAW_DIR}")
    for p in paths:
        ingest_file(p, force=force)


def cmd_status() -> None:
    from .db import connect
    with connect() as con:
        rows = con.execute("""
            SELECT data_month, rows_loaded, duration_sec, finished_at
            FROM (SELECT *, row_number() OVER (PARTITION BY data_month ORDER BY finished_at DESC) rn
                  FROM meta.ingestion_log WHERE status = 'success') x
            WHERE rn = 1 ORDER BY data_month""").fetchall()
        failed = con.execute("SELECT count(*) FROM meta.ingestion_log WHERE status = 'failed'").fetchone()[0]
    print(f"  {'month':<9}{'rows':>10}{'load s':>9}  last loaded")
    for m, n, d, t in rows:
        print(f"  {m:%Y-%m}  {n:>10,}{d:>9}  {t:%Y-%m-%d %H:%M}")
    print(f"  failed attempts logged: {failed}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="get data -> ingest -> dbt build -> report")
    r.add_argument("--source", choices=["fake", "real"], default="fake")
    r.add_argument("--months", default="2025-01:2025-03")
    r.add_argument("--rows", type=int, default=60_000, help="rows per fake month (real Jan 2025 ~ 540K)")
    r.add_argument("--force", action="store_true", help="reload files even if already loaded")

    g = sub.add_parser("get", help="generate fake files or download real ones")
    g.add_argument("--source", choices=["fake", "real"], default="fake")
    g.add_argument("--months", default="2025-01:2025-03")
    g.add_argument("--rows", type=int, default=60_000)

    i = sub.add_parser("ingest", help="load every file in data/raw")
    i.add_argument("--force", action="store_true")

    sub.add_parser("transform", help="dbt seed + run + test")
    sub.add_parser("report", help="build reports/flight_delays.html")
    sub.add_parser("status", help="show what has been loaded")
    a = ap.parse_args()

    t0 = time.perf_counter()
    if a.cmd in ("run", "get"):
        print("[1/4] get data")
        paths = cmd_get(a.source, parse_months(a.months), a.rows)
        if a.cmd == "run":
            print("[2/4] ingest")
            cmd_ingest(paths, a.force)
            print("[3/4] transform + test")
            from .transform import dbt
            dbt("build")
            print("[4/4] report")
            from .report import build_report
            build_report()
    elif a.cmd == "ingest":
        cmd_ingest(force=a.force)
    elif a.cmd == "transform":
        from .transform import dbt
        dbt("build")
    elif a.cmd == "report":
        from .report import build_report
        build_report()
    elif a.cmd == "status":
        cmd_status()
    print(f"done in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()

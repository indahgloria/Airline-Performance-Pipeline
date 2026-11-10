import psycopg

from .config import PG, ROOT


def connect() -> psycopg.Connection:
    return psycopg.connect(**{k: v for k, v in PG.items() if v != ""})


def bootstrap() -> None:
    with connect() as con:
        con.execute((ROOT / "sql" / "bootstrap.sql").read_text())

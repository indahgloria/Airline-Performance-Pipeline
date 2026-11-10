import subprocess
import sys

from .config import DBT_DIR


def dbt(*args: str) -> None:
    print(f"  dbt    {' '.join(args)}")
    cmd = ["dbt", *args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    if subprocess.run(cmd).returncode != 0:
        sys.exit(f"dbt {' '.join(args)} failed")

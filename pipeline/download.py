"""Download real monthly files from the Bureau of Transportation Statistics.

Files land in data/raw/ with the same names the fake generator uses, so nothing downstream
changes. Already-downloaded months are skipped.
"""
import shutil
import urllib.request
from pathlib import Path

from .config import BTS_URL, BTS_ZIP_NAME, RAW_DIR


def download_month(year: int, month: int, force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / BTS_ZIP_NAME.format(year=year, month=month)
    if dest.exists() and not force:
        print(f"  skip   {dest.name} (already downloaded)")
        return dest
    url = BTS_URL.format(year=year, month=month)
    print(f"  fetch  {url}")
    tmp = dest.with_suffix(".part")  # write to a temp file so a dropped connection never leaves a half file
    req = urllib.request.Request(url, headers={"User-Agent": "airline-performance-pipeline"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)
    tmp.rename(dest)
    print(f"  saved  {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest

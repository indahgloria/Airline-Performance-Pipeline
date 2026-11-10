"""Optional S3 landing zone for raw files.

Turn it on by setting S3_BUCKET. Then:
  - every file the pipeline generates or downloads is uploaded to s3://<bucket>/<prefix>/
  - `python -m pipeline ingest` first pulls anything in S3 that isn't on this machine yet

S3 becomes the durable copy of the raw data, so any machine (a laptop, a CI runner, a
scheduled job) can rebuild the database from it. Re-uploads and re-downloads are skipped
when the file is already there with the same size; the SHA-256 check in ingest.py is still
what guarantees a file is never loaded twice.

Credentials come from the normal AWS chain (`aws configure`, env vars, or an IAM role),
never from this repo.
"""
from pathlib import Path

from . import config

RAW_SUFFIXES = (".zip", ".csv")


def _client():
    import boto3
    return boto3.client("s3")


def _remote_size(s3, key: str) -> int | None:
    from botocore.exceptions import ClientError
    try:
        return s3.head_object(Bucket=config.S3_BUCKET, Key=key)["ContentLength"]
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def upload(path: Path) -> str:
    s3 = _client()
    key = config.S3_PREFIX + path.name
    uri = f"s3://{config.S3_BUCKET}/{key}"
    if _remote_size(s3, key) == path.stat().st_size:
        print(f"  skip   {uri} (already in S3)")
        return "skipped"
    s3.upload_file(str(path), config.S3_BUCKET, key)
    print(f"  put    {uri} ({path.stat().st_size / 1e6:.1f} MB)")
    return "uploaded"


def sync_down() -> list[Path]:
    """Download every raw file under the S3 prefix that is missing (or different) locally."""
    s3 = _client()
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    pulled = []
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=config.S3_BUCKET, Prefix=config.S3_PREFIX)
    for page in pages:
        for obj in page.get("Contents", []):
            name = obj["Key"][len(config.S3_PREFIX):]
            if "/" in name or not name.endswith(RAW_SUFFIXES):
                continue
            dest = config.RAW_DIR / name
            if dest.exists() and dest.stat().st_size == obj["Size"]:
                continue
            tmp = dest.with_suffix(dest.suffix + ".part")
            s3.download_file(config.S3_BUCKET, obj["Key"], str(tmp))
            tmp.rename(dest)
            print(f"  pull   s3://{config.S3_BUCKET}/{obj['Key']}")
            pulled.append(dest)
    if not pulled:
        print(f"  s3     nothing new in s3://{config.S3_BUCKET}/{config.S3_PREFIX}")
    return pulled

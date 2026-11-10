"""S3 landing zone, tested against a mocked S3 (moto), so no AWS account is needed."""
import boto3
import pytest
from moto import mock_aws

from pipeline import config, s3

BUCKET = "test-airline-raw"


@pytest.fixture
def bucket(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)  # always use the in-process mock
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(config, "S3_BUCKET", BUCKET)
    monkeypatch.setattr(config, "S3_PREFIX", "raw/bts/")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket=BUCKET)
        yield tmp_path


def make_file(directory, name="flights_2025_1.zip", data=b"x" * 1000):
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_bytes(data)
    return p


def test_upload_is_idempotent(bucket):
    p = make_file(bucket / "local")
    assert s3.upload(p) == "uploaded"
    assert s3.upload(p) == "skipped"
    keys = [o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert keys == ["raw/bts/flights_2025_1.zip"]


def test_changed_file_is_reuploaded(bucket):
    p = make_file(bucket / "local")
    s3.upload(p)
    p.write_bytes(b"y" * 2000)
    assert s3.upload(p) == "uploaded"


def test_sync_down_pulls_only_missing_files(bucket):
    a = make_file(bucket / "local", "a.zip")
    b = make_file(bucket / "local", "b.csv")
    s3.upload(a)
    s3.upload(b)
    boto3.client("s3").put_object(Bucket=BUCKET, Key="raw/bts/notes.txt", Body=b"ignore me")

    make_file(config.RAW_DIR, "a.zip")  # already present locally
    pulled = s3.sync_down()
    assert [p.name for p in pulled] == ["b.csv"]
    assert (config.RAW_DIR / "b.csv").read_bytes() == b"x" * 1000
    assert s3.sync_down() == []

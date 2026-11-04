"""Invoice file storage: Vultr Object Storage (S3-compatible) or local disk."""

from functools import lru_cache
from pathlib import Path

from .config import get_settings


class LocalStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class S3Store:
    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str):
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key
        )
        try:
            self.client.head_bucket(Bucket=bucket)
        except Exception:
            self.client.create_bucket(Bucket=bucket)

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()


@lru_cache
def get_store():
    s = get_settings()
    if s.s3_endpoint:
        return S3Store(s.s3_endpoint, s.s3_bucket, s.s3_access_key, s.s3_secret_key)
    return LocalStore(s.local_storage_dir)

"""B2 access through its S3-compatible endpoint via boto3.

We use boto3 instead of b2sdk because the heavy paths (presigned URLs,
restricted-ACL puts) are S3-shaped and boto3 is already a project
dependency. Each process gets its own client lazily, which is the
process-safety guarantee — no shared mutable state crosses fork().
"""
from __future__ import annotations

import os
import threading
from typing import Optional

import boto3
from botocore.client import Config


_client_lock = threading.Lock()
_client = None
_client_pid: Optional[int] = None


def _get_client():
    """Per-process boto3 client. Recreated after fork so descriptors aren't shared."""
    global _client, _client_pid
    pid = os.getpid()
    if _client is not None and _client_pid == pid:
        return _client
    with _client_lock:
        if _client is None or _client_pid != pid:
            _client = boto3.client(
                "s3",
                endpoint_url=os.getenv("B2_ENDPOINT", "https://s3.us-east-005.backblazeb2.com"),
                aws_access_key_id=os.getenv("B2_ACCOUNT_ID"),
                aws_secret_access_key=os.getenv("B2_APPLICATION_KEY"),
                config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
            )
            _client_pid = pid
    return _client


def _bucket() -> str:
    name = os.getenv("B2_BUCKET_NAME")
    if not name:
        raise RuntimeError("B2_BUCKET_NAME is not configured")
    return name


def upload_bytes_with_acl(
    data: bytes,
    object_key: str,
    *,
    content_type: str = "application/octet-stream",
    private: bool = True,
) -> str:
    """Upload bytes with a restricted ACL. Returns the object key.

    URLs are not returned — callers should mint a presigned URL at read time
    to keep the bucket private and the link TTL-bounded.
    """
    client = _get_client()
    extra = {"ContentType": content_type}
    if private:
        extra["ACL"] = "private"
    client.put_object(Bucket=_bucket(), Key=object_key, Body=data, **extra)
    return object_key


def generate_presigned_url(object_key: str, ttl_seconds: int) -> str:
    client = _get_client()
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": _bucket(), "Key": object_key},
        ExpiresIn=ttl_seconds,
    )


def fetch_bytes(object_key: str) -> bytes:
    client = _get_client()
    obj = client.get_object(Bucket=_bucket(), Key=object_key)
    return obj["Body"].read()

"""S3 helpers for cloud-native fusion-layer workflows."""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote_plus, urlparse

import pandas as pd
import yaml


@dataclass(frozen=True)
class S3Location:
    """Parsed S3 location with bucket and key."""

    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


def parse_s3_uri(s3_uri: str) -> S3Location:
    """Parse an S3 URI into bucket and key components."""

    parsed = urlparse(str(s3_uri))
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise ValueError(f"Invalid S3 URI: {s3_uri!r}. Expected format s3://bucket/key")
    key = parsed.path.lstrip("/")
    if not key:
        raise ValueError(f"S3 URI must include an object key: {s3_uri!r}")
    return S3Location(bucket=parsed.netloc, key=key)


def build_s3_uri(bucket: str, key: str) -> str:
    """Build an S3 URI from bucket and key values."""

    cleaned_bucket = str(bucket).strip()
    cleaned_key = str(key).strip().lstrip("/")
    if not cleaned_bucket or not cleaned_key:
        raise ValueError("Both bucket and key are required to build an S3 URI.")
    return f"s3://{cleaned_bucket}/{cleaned_key}"


def decode_s3_key(key: str) -> str:
    """Decode URL-encoded S3 object keys from event notifications."""

    return unquote_plus(str(key))


def read_s3_bytes(s3_uri: str, s3_client: Any) -> bytes:
    """Read object bytes from S3."""

    location = parse_s3_uri(s3_uri)
    response = s3_client.get_object(Bucket=location.bucket, Key=location.key)
    return response["Body"].read()


def read_csv_from_s3(s3_uri: str, s3_client: Any) -> pd.DataFrame:
    """Load a CSV object from S3 into a dataframe."""

    payload = read_s3_bytes(s3_uri, s3_client)
    return pd.read_csv(io.BytesIO(payload), dtype={"email_id": "string"})


def list_s3_objects(
    bucket: str,
    prefix: str,
    s3_client: Any,
    max_keys: int = 1000,
) -> list[dict[str, Any]]:
    """List S3 objects under a prefix with metadata.

    Returns metadata records with `bucket`, `key`, `size`, and `last_modified`.
    """

    cleaned_bucket = str(bucket).strip()
    cleaned_prefix = str(prefix).strip().lstrip("/")
    if not cleaned_bucket:
        raise ValueError("bucket is required.")
    if not cleaned_prefix:
        raise ValueError("prefix is required.")

    records: list[dict[str, Any]] = []

    if hasattr(s3_client, "get_paginator"):
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=cleaned_bucket, Prefix=cleaned_prefix):
            for item in page.get("Contents", []):
                records.append(
                    {
                        "bucket": cleaned_bucket,
                        "key": str(item.get("Key", "")),
                        "size": int(item.get("Size", 0)),
                        "last_modified": item.get("LastModified"),
                    }
                )
                if len(records) >= max_keys:
                    return records[:max_keys]
        return records[:max_keys]

    # Fallback for simple test stubs that only implement list_objects_v2.
    response = s3_client.list_objects_v2(Bucket=cleaned_bucket, Prefix=cleaned_prefix)
    for item in response.get("Contents", []):
        records.append(
            {
                "bucket": cleaned_bucket,
                "key": str(item.get("Key", "")),
                "size": int(item.get("Size", 0)),
                "last_modified": item.get("LastModified"),
            }
        )
    return records[:max_keys]


def _sort_key_for_s3_record(record: dict[str, Any]) -> tuple[float, str]:
    """Build a deterministic sort key for S3 record freshness."""

    last_modified = record.get("last_modified")
    if isinstance(last_modified, datetime):
        timestamp = last_modified.timestamp()
    else:
        timestamp = 0.0
    return (timestamp, str(record.get("key", "")))


def get_latest_s3_object(
    bucket: str,
    prefix: str,
    s3_client: Any,
    suffix: str | None = ".csv",
) -> dict[str, Any]:
    """Get metadata for the latest object under a prefix.

    If `suffix` is provided, only keys ending in that suffix are considered.
    """

    all_objects = list_s3_objects(bucket=bucket, prefix=prefix, s3_client=s3_client)
    if suffix:
        normalized_suffix = str(suffix)
        candidates = [record for record in all_objects if str(record.get("key", "")).endswith(normalized_suffix)]
    else:
        candidates = all_objects

    if not candidates:
        suffix_text = f" with suffix {suffix!r}" if suffix else ""
        raise FileNotFoundError(
            f"No S3 objects found in s3://{bucket}/{prefix}{suffix_text}."
        )

    latest = sorted(candidates, key=_sort_key_for_s3_record, reverse=True)[0]
    latest["uri"] = build_s3_uri(str(latest["bucket"]), str(latest["key"]))
    return latest


def write_dataframe_to_s3_csv(dataframe: pd.DataFrame, s3_uri: str, s3_client: Any) -> None:
    """Serialize and write a dataframe to an S3 CSV object."""

    location = parse_s3_uri(s3_uri)
    csv_payload = dataframe.to_csv(index=False).encode("utf-8")
    s3_client.put_object(
        Bucket=location.bucket,
        Key=location.key,
        Body=csv_payload,
        ContentType="text/csv",
    )


def write_json_to_s3(payload: dict[str, Any], s3_uri: str, s3_client: Any) -> None:
    """Serialize and write a JSON payload to S3."""

    location = parse_s3_uri(s3_uri)
    json_payload = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    s3_client.put_object(
        Bucket=location.bucket,
        Key=location.key,
        Body=json_payload,
        ContentType="application/json",
    )


def load_yaml_from_s3(s3_uri: str, s3_client: Any) -> dict[str, Any]:
    """Load and parse a YAML file stored in S3."""

    payload = read_s3_bytes(s3_uri, s3_client)
    loaded = yaml.safe_load(payload.decode("utf-8"))
    return loaded or {}


def download_s3_object_to_tempfile(
    s3_uri: str,
    s3_client: Any,
    suffix: str = "",
) -> Path:
    """Download an S3 object to a local temp file and return its path."""

    payload = read_s3_bytes(s3_uri, s3_client)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(payload)
        return Path(temp_file.name)


def build_output_uri_from_input(
    input_s3_uri: str,
    fusion_method: str,
    output_bucket: str | None = None,
    output_prefix: str = "fusion-output",
    output_filename: str | None = None,
) -> str:
    """Build a default output S3 URI based on the input object location."""

    input_location = parse_s3_uri(input_s3_uri)
    bucket = output_bucket or input_location.bucket
    input_name = PurePosixPath(input_location.key).stem
    filename = output_filename or f"{input_name}_{fusion_method}_predictions.csv"
    prefix = str(output_prefix).strip().strip("/")
    key = f"{prefix}/{filename}" if prefix else filename
    return build_s3_uri(bucket, key)
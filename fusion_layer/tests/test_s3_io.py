"""Tests for S3 utility helpers used by the Lambda runtime."""

from __future__ import annotations

from datetime import datetime, timedelta
import io

import pandas as pd
import pytest

from src.s3_io import (
    build_output_uri_from_input,
    build_s3_uri,
    decode_s3_key,
    get_latest_s3_object,
    list_s3_objects,
    parse_s3_uri,
    read_csv_from_s3,
    write_dataframe_to_s3_csv,
)


class StubS3Client:
    """Small in-memory S3 stub for unit testing."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.listing: dict[tuple[str, str], list[dict[str, object]]] = {}

    def get_object(self, Bucket: str, Key: str):  # noqa: N803
        payload = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(payload)}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str):  # noqa: N803
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def list_objects_v2(self, Bucket: str, Prefix: str):  # noqa: N803
        return {"Contents": self.listing.get((Bucket, Prefix), [])}


def test_parse_s3_uri_and_build_s3_uri() -> None:
    uri = build_s3_uri("fusion-bucket", "/input/inference.csv")
    parsed = parse_s3_uri(uri)
    assert uri == "s3://fusion-bucket/input/inference.csv"
    assert parsed.bucket == "fusion-bucket"
    assert parsed.key == "input/inference.csv"


def test_parse_s3_uri_rejects_invalid_uri() -> None:
    with pytest.raises(ValueError, match="Invalid S3 URI"):
        parse_s3_uri("https://example.com/not-s3")


def test_decode_s3_key_handles_event_encoded_spaces() -> None:
    assert decode_s3_key("fusion-input%2Fsample+file.csv") == "fusion-input/sample file.csv"


def test_s3_csv_round_trip() -> None:
    stub = StubS3Client()
    dataframe = pd.DataFrame(
        [
            {"email_id": "e1", "p_header": 0.8, "p_body": 0.7, "p_malware": 0.9},
            {"email_id": "e2", "p_header": 0.1, "p_body": 0.2, "p_malware": None},
        ]
    )

    target_uri = "s3://fusion-bucket/fusion-input/inference.csv"
    write_dataframe_to_s3_csv(dataframe, target_uri, stub)
    loaded = read_csv_from_s3(target_uri, stub)

    assert list(loaded.columns) == ["email_id", "p_header", "p_body", "p_malware"]
    assert loaded["email_id"].tolist() == ["e1", "e2"]
    assert loaded["p_header"].tolist() == pytest.approx([0.8, 0.1])


def test_build_output_uri_from_input_uses_defaults() -> None:
    output_uri = build_output_uri_from_input(
        input_s3_uri="s3://fusion-bucket/fusion-input/inference.csv",
        fusion_method="soft_voting",
    )
    assert output_uri == "s3://fusion-bucket/fusion-output/inference_soft_voting_predictions.csv"


def test_list_s3_objects_and_get_latest_s3_object() -> None:
    stub = StubS3Client()
    now = datetime.utcnow()
    bucket = "fusion-bucket"
    prefix = "fusion-input/live/"
    stub.listing[(bucket, prefix)] = [
        {
            "Key": "fusion-input/live/batch_001.csv",
            "Size": 100,
            "LastModified": now - timedelta(minutes=5),
        },
        {
            "Key": "fusion-input/live/batch_002.csv",
            "Size": 120,
            "LastModified": now,
        },
    ]

    listed = list_s3_objects(bucket=bucket, prefix=prefix, s3_client=stub)
    assert len(listed) == 2
    latest = get_latest_s3_object(bucket=bucket, prefix=prefix, s3_client=stub)
    assert latest["key"] == "fusion-input/live/batch_002.csv"
    assert latest["uri"] == "s3://fusion-bucket/fusion-input/live/batch_002.csv"
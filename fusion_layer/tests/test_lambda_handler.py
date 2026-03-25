"""Tests for Lambda + S3 runtime behavior."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from src import lambda_handler as lambda_runtime


class StubS3Client:
    """In-memory S3 client for Lambda tests."""

    def __init__(self, objects: dict[tuple[str, str], bytes] | None = None) -> None:
        self.objects = objects or {}

    def get_object(self, Bucket: str, Key: str):  # noqa: N803
        payload = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(payload)}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str):  # noqa: N803
        _ = ContentType
        self.objects[(Bucket, Key)] = Body


class StubBoto3:
    """Simple boto3 shim exposing a single S3 client."""

    def __init__(self, s3_client: StubS3Client) -> None:
        self._s3_client = s3_client

    def client(self, name: str):
        if name != "s3":
            raise ValueError(f"Unexpected client name: {name}")
        return self._s3_client


def test_resolve_input_s3_uri_from_direct_payload() -> None:
    event = {"input_s3_uri": "s3://bucket/fusion-input/inference.csv"}
    resolved = lambda_runtime._resolve_input_s3_uri(event)
    assert resolved == "s3://bucket/fusion-input/inference.csv"


def test_resolve_input_s3_uri_from_s3_event_record() -> None:
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "fusion-bucket"},
                    "object": {"key": "fusion-input%2Finference+data.csv"},
                }
            }
        ]
    }
    resolved = lambda_runtime._resolve_input_s3_uri(event)
    assert resolved == "s3://fusion-bucket/fusion-input/inference data.csv"


def test_resolve_input_s3_uri_rejects_missing_source() -> None:
    with pytest.raises(ValueError, match="Missing input location"):
        lambda_runtime._resolve_input_s3_uri({})


def test_lambda_handler_soft_voting_s3_round_trip(monkeypatch) -> None:
    input_csv = (
        "email_id,p_header,p_body,p_malware\n"
        "e1,0.88,0.77,0.91\n"
        "e2,0.14,0.20,\n"
    ).encode("utf-8")

    stub_s3 = StubS3Client(
        objects={
            ("fusion-bucket", "fusion-input/sample.csv"): input_csv,
        }
    )

    monkeypatch.setattr(lambda_runtime, "boto3", StubBoto3(stub_s3))

    event = {
        "input_s3_uri": "s3://fusion-bucket/fusion-input/sample.csv",
        "output_s3_uri": "s3://fusion-bucket/fusion-output/sample_predictions.csv",
        "fusion_method": "soft_voting",
    }

    response = lambda_runtime.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert response["fusion_method"] == "soft_voting"
    assert response["rows_scored"] == 2
    assert response["output_s3_uri"] == "s3://fusion-bucket/fusion-output/sample_predictions.csv"

    output_payload = stub_s3.objects[("fusion-bucket", "fusion-output/sample_predictions.csv")]
    output_df = pd.read_csv(io.BytesIO(output_payload))

    assert list(output_df.columns) == [
        "email_id",
        "final_score",
        "final_label",
        "risk_level",
        "models_used",
        "fusion_method",
    ]
    assert output_df["email_id"].tolist() == ["e1", "e2"]
    assert set(output_df["fusion_method"]) == {"soft_voting"}

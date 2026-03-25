"""Tests for localhost S3 testing web app behavior."""

from __future__ import annotations

from datetime import datetime
import io

import pandas as pd
import pytest

pytest.importorskip("flask")
from src.web_app import create_app


class StubS3Client:
    """In-memory S3 client for web-app tests."""

    def __init__(self, objects: dict[tuple[str, str], bytes] | None = None) -> None:
        self.objects = objects or {}
        self.listing: dict[tuple[str, str], list[dict[str, object]]] = {}

    def get_object(self, Bucket: str, Key: str):  # noqa: N803
        payload = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(payload)}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str):  # noqa: N803
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def list_objects_v2(self, Bucket: str, Prefix: str):  # noqa: N803
        return {"Contents": self.listing.get((Bucket, Prefix), [])}


class StubBoto3:
    """Simple boto3 shim exposing a fixed S3 client."""

    def __init__(self, s3_client: StubS3Client) -> None:
        self._s3_client = s3_client

    def client(self, name: str):
        if name != "s3":
            raise ValueError(name)
        return self._s3_client


def test_web_app_health_endpoint() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/api/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload == {"ok": True, "status": "ready"}


def test_web_app_run_s3_fusion_soft_voting(monkeypatch) -> None:
    input_csv = (
        "email_id,p_header,p_body,p_malware\n"
        "e1,0.80,0.70,0.90\n"
        "e2,0.10,0.20,\n"
    ).encode("utf-8")

    stub_s3 = StubS3Client(
        objects={
            ("fusion-bucket", "fusion-input/inference.csv"): input_csv,
        }
    )

    import src.web_app as web_runtime

    monkeypatch.setattr(web_runtime, "boto3", StubBoto3(stub_s3))

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/run-s3-fusion",
        json={
            "input_s3_uri": "s3://fusion-bucket/fusion-input/inference.csv",
            "fusion_method": "soft_voting",
            "output_s3_uri": "s3://fusion-bucket/fusion-output/predictions.csv",
            "write_output_to_s3": True,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["rows_scored"] == 2
    assert payload["output_s3_uri"] == "s3://fusion-bucket/fusion-output/predictions.csv"

    output_bytes = stub_s3.objects[("fusion-bucket", "fusion-output/predictions.csv")]
    output_df = pd.read_csv(io.BytesIO(output_bytes))
    assert list(output_df.columns) == [
        "email_id",
        "final_score",
        "final_label",
        "risk_level",
        "models_used",
        "fusion_method",
    ]


def test_web_app_run_local_input_and_local_output(monkeypatch, tmp_path) -> None:
    local_input = tmp_path / "local_inference.csv"
    local_output = tmp_path / "local_predictions.csv"
    local_input.write_text(
        "email_id,p_header,p_body,p_malware\n"
        "e1,0.88,0.77,0.91\n"
        "e2,0.14,0.20,\n",
        encoding="utf-8",
    )

    import src.web_app as web_runtime

    monkeypatch.setattr(web_runtime, "boto3", StubBoto3(StubS3Client()))

    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/run-s3-fusion",
        json={
            "input_source": "local",
            "local_input_path": str(local_input),
            "fusion_method": "soft_voting",
            "write_output_to_s3": False,
            "write_output_local": True,
            "local_output_path": str(local_output),
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["input_source"] == "local"
    assert payload["written_to_s3"] is False
    assert payload["written_to_local"] is True
    assert payload["local_output_path"] == str(local_output)
    assert local_output.exists()


def test_web_app_run_s3_latest_from_prefix(monkeypatch) -> None:
    latest_key = "parsed/fusion-input/live_batch_002.csv"
    latest_uri = f"s3://fusion-bucket/{latest_key}"
    latest_csv = (
        "email_id,p_header,p_body,p_malware\n"
        "e1,0.81,0.71,0.92\n"
        "e2,0.12,0.23,\n"
    ).encode("utf-8")

    stub_s3 = StubS3Client(objects={("fusion-bucket", latest_key): latest_csv})
    stub_s3.listing[("fusion-bucket", "parsed/fusion-input/")] = [
        {
            "Key": "parsed/fusion-input/live_batch_001.csv",
            "Size": 100,
            "LastModified": datetime(2026, 1, 1, 0, 0, 0),
        },
        {
            "Key": latest_key,
            "Size": 110,
            "LastModified": datetime(2026, 1, 1, 0, 5, 0),
        },
    ]

    import src.web_app as web_runtime

    monkeypatch.setattr(web_runtime, "boto3", StubBoto3(stub_s3))

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/run-s3-fusion",
        json={
            "input_source": "s3",
            "use_latest_from_prefix": True,
            "source_bucket": "fusion-bucket",
            "source_prefix": "parsed/fusion-input/",
            "fusion_method": "soft_voting",
            "write_output_to_s3": False,
            "write_output_local": False,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["used_latest_from_prefix"] is True
    assert payload["input_s3_uri"] == latest_uri
    assert payload["latest_source_key"] == latest_key


def test_web_app_run_s3_latest_from_prefix_no_new_data(monkeypatch) -> None:
    latest_key = "parsed/fusion-input/live_batch_002.csv"
    latest_csv = (
        "email_id,p_header,p_body,p_malware\n"
        "e1,0.81,0.71,0.92\n"
    ).encode("utf-8")

    stub_s3 = StubS3Client(objects={("fusion-bucket", latest_key): latest_csv})
    stub_s3.listing[("fusion-bucket", "parsed/fusion-input/")] = [
        {
            "Key": latest_key,
            "Size": 110,
            "LastModified": datetime(2026, 1, 1, 0, 5, 0),
        },
    ]

    import src.web_app as web_runtime

    monkeypatch.setattr(web_runtime, "boto3", StubBoto3(stub_s3))

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/run-s3-fusion",
        json={
            "input_source": "s3",
            "use_latest_from_prefix": True,
            "source_bucket": "fusion-bucket",
            "source_prefix": "parsed/fusion-input/",
            "last_seen_key": latest_key,
            "fusion_method": "soft_voting",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["no_new_data"] is True
    assert payload["rows_scored"] == 0
    assert payload["latest_source_key"] == latest_key


def test_web_app_latest_from_prefix_requires_bucket_and_prefix(monkeypatch) -> None:
    import src.web_app as web_runtime

    monkeypatch.setattr(web_runtime, "boto3", StubBoto3(StubS3Client()))

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/run-s3-fusion",
        json={
            "input_source": "s3",
            "use_latest_from_prefix": True,
            "fusion_method": "soft_voting",
        },
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert "source_bucket and source_prefix" in payload["error"]

"""AWS Lambda handler for fusion inference using S3 inputs and outputs."""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import boto3
except ImportError:  # pragma: no cover - handled at runtime if boto3 is unavailable
    boto3 = None  # type: ignore[assignment]

from src.inference import SUPPORTED_FUSION_METHODS
from src.loaders import load_inference_dataframe_from_dataframe
from src.logistic_fusion import LogisticFusionModel
from src.s3_io import (
    build_output_uri_from_input,
    build_s3_uri,
    decode_s3_key,
    download_s3_object_to_tempfile,
    load_yaml_from_s3,
    read_csv_from_s3,
    write_dataframe_to_s3_csv,
)
from src.soft_voting import SoftVotingFusion
from src.utils import get_project_root, load_config, resolve_project_path


def _resolve_config(event: dict[str, Any], s3_client: Any) -> dict[str, Any]:
    """Resolve runtime configuration from event payload, env, or local config."""

    config_uri = event.get("config_s3_uri") or os.getenv("FUSION_CONFIG_S3_URI")
    if config_uri:
        return load_yaml_from_s3(str(config_uri), s3_client)
    return load_config(None)


def _resolve_input_s3_uri(event: dict[str, Any]) -> str:
    """Resolve the input S3 URI from direct payload or S3 event shape."""

    if event.get("input_s3_uri"):
        return str(event["input_s3_uri"])

    records = event.get("Records")
    if records and isinstance(records, list):
        record = records[0]
        bucket = record.get("s3", {}).get("bucket", {}).get("name")
        key = record.get("s3", {}).get("object", {}).get("key")
        if bucket and key:
            return build_s3_uri(str(bucket), decode_s3_key(str(key)))

    raise ValueError(
        "Missing input location. Provide event['input_s3_uri'] or invoke using an S3 event payload."
    )


def _resolve_output_s3_uri(event: dict[str, Any], input_s3_uri: str, fusion_method: str) -> str:
    """Resolve destination S3 URI for fusion output."""

    if event.get("output_s3_uri"):
        return str(event["output_s3_uri"])

    output_bucket = event.get("output_bucket") or os.getenv("FUSION_OUTPUT_BUCKET")
    output_prefix = event.get("output_prefix") or os.getenv("FUSION_OUTPUT_PREFIX", "fusion-output")
    output_filename = event.get("output_filename")
    return build_output_uri_from_input(
        input_s3_uri=input_s3_uri,
        fusion_method=fusion_method,
        output_bucket=str(output_bucket) if output_bucket else None,
        output_prefix=str(output_prefix),
        output_filename=str(output_filename) if output_filename else None,
    )


def _resolve_fusion_method(event: dict[str, Any], config: dict[str, Any]) -> str:
    """Resolve fusion method from event/env/config with validation."""

    method = (
        event.get("fusion_method")
        or os.getenv("FUSION_METHOD")
        or config.get("fusion", {}).get("primary_method", "logistic_regression_stacking")
    )
    method = str(method)
    if method not in SUPPORTED_FUSION_METHODS:
        raise ValueError(
            f"fusion_method must be one of {SUPPORTED_FUSION_METHODS}, got {method!r}."
        )
    return method


def _resolve_model_artifact_location(event: dict[str, Any], config: dict[str, Any]) -> str | None:
    """Resolve logistic model artifact location for Lambda inference.

    Priority:
    1) event['model_artifact_uri'] / event['model_artifact_s3_uri']
    2) env FUSION_MODEL_URI / FUSION_MODEL_S3_URI
    3) config artifacts.model_path (local path or s3 URI)
    """

    event_uri = event.get("model_artifact_uri")
    if event_uri:
        return str(event_uri)

    event_uri = event.get("model_artifact_s3_uri")
    if event_uri:
        return str(event_uri)

    env_uri = os.getenv("FUSION_MODEL_URI")
    if env_uri:
        return env_uri

    env_uri = os.getenv("FUSION_MODEL_S3_URI")
    if env_uri:
        return env_uri

    configured_model_path = config.get("artifacts", {}).get("model_path")
    if configured_model_path:
        return str(configured_model_path).strip()
    return None


def _run_fusion(
    inference_df,
    fusion_method: str,
    threshold: float,
    model_artifact_location: str | None,
    s3_client: Any,
):
    """Execute soft-voting or logistic-stacking fusion."""

    if fusion_method == "soft_voting":
        fusion_engine = SoftVotingFusion(threat_threshold=threshold)
        return fusion_engine.predict(inference_df)

    if not model_artifact_location:
        raise ValueError(
            "logistic_regression_stacking requires a model artifact location. "
            "Provide model_artifact_uri/model_artifact_s3_uri in the event, "
            "or set FUSION_MODEL_URI/FUSION_MODEL_S3_URI."
        )

    if str(model_artifact_location).startswith("s3://"):
        artifact_local_path = download_s3_object_to_tempfile(
            str(model_artifact_location),
            s3_client,
            suffix=".joblib",
        )
    else:
        artifact_local_path = resolve_project_path(str(model_artifact_location))

    fusion_engine = LogisticFusionModel.load(artifact_local_path)
    return fusion_engine.predict(inference_df)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint for S3-driven fusion inference.

    Supported event shapes:
    1) Direct invocation payload
       {
         "input_s3_uri": "s3://bucket/fusion-input/inference.csv",
         "output_s3_uri": "s3://bucket/fusion-output/predictions.csv",
         "fusion_method": "logistic_regression_stacking",
         "model_artifact_uri": "s3://bucket/artifacts/logistic_fusion_model.joblib",
         "config_s3_uri": "s3://bucket/config/fusion_config.yaml"
       }

    2) Native S3 event notification (object-created)
       - bucket/key are read from event['Records'][0]['s3']
       - output URI is derived from output bucket/prefix settings
    """

    _ = context
    if boto3 is None:
        raise ImportError("boto3 is required to run the Lambda handler. Install boto3>=1.34.0")
    s3_client = boto3.client("s3")

    config = _resolve_config(event, s3_client)
    fusion_method = _resolve_fusion_method(event, config)
    input_s3_uri = _resolve_input_s3_uri(event)
    output_s3_uri = _resolve_output_s3_uri(event, input_s3_uri, fusion_method)

    threshold = float(config.get("thresholds", {}).get("final_label", 0.50))
    model_artifact_location = _resolve_model_artifact_location(event, config)

    raw_df = read_csv_from_s3(input_s3_uri, s3_client)
    inference_df = load_inference_dataframe_from_dataframe(raw_df)
    predictions = _run_fusion(
        inference_df=inference_df,
        fusion_method=fusion_method,
        threshold=threshold,
        model_artifact_location=model_artifact_location,
        s3_client=s3_client,
    )
    write_dataframe_to_s3_csv(predictions, output_s3_uri, s3_client)

    return {
        "statusCode": 200,
        "message": "Fusion inference completed.",
        "fusion_method": fusion_method,
        "input_s3_uri": input_s3_uri,
        "output_s3_uri": output_s3_uri,
        "rows_scored": int(len(predictions)),
        "output_columns": list(predictions.columns),
        "project_root": str(get_project_root()),
    }


def _json_default_serializer(value: Any) -> str:
    """Fallback serializer for Lambda local test harness output."""

    return str(value)


if __name__ == "__main__":
    sample_event = {
        "input_s3_uri": "s3://your-bucket/fusion-input/sample_fusion_inference.csv",
        "fusion_method": "soft_voting",
        "output_prefix": "fusion-output",
    }
    print(json.dumps(lambda_handler(sample_event, None), indent=2, default=_json_default_serializer))
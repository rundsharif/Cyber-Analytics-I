"""Localhost web app for S3-backed fusion testing workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import boto3
from flask import Flask, jsonify, render_template, request

from src.inference import SUPPORTED_FUSION_METHODS
from src.loaders import (
    load_inference_dataframe,
    load_inference_dataframe_from_dataframe,
    write_output_dataframe,
)
from src.logistic_fusion import LogisticFusionModel
from src.s3_io import (
    build_output_uri_from_input,
    download_s3_object_to_tempfile,
    get_latest_s3_object,
    parse_s3_uri,
    read_csv_from_s3,
    write_dataframe_to_s3_csv,
)
from src.soft_voting import SoftVotingFusion
from src.utils import load_config, resolve_project_path


def _coerce_bool(value: Any, default: bool = True) -> bool:
    """Coerce payload values into boolean flags."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _resolve_model_artifact_path(
    fusion_method: str,
    artifact_uri: str | None,
    config: dict[str, Any],
    s3_client: Any,
) -> Path | None:
    """Resolve the logistic model artifact for local web app inference."""

    if fusion_method != "logistic_regression_stacking":
        return None

    candidate = (artifact_uri or str(config.get("artifacts", {}).get("model_path", ""))).strip()
    if not candidate:
        raise ValueError(
            "Missing model artifact path/URI for logistic_regression_stacking."
        )

    if candidate.startswith("s3://"):
        return download_s3_object_to_tempfile(candidate, s3_client, suffix=".joblib")
    return resolve_project_path(candidate)


def _load_input_dataframe(payload: dict[str, Any], s3_client: Any):
    """Load inference rows from either S3 URI or local CSV path."""

    input_source = str(payload.get("input_source", "s3")).strip().lower()
    if input_source not in {"s3", "local"}:
        raise ValueError("input_source must be either 's3' or 'local'.")

    if input_source == "s3":
        use_latest_from_prefix = _coerce_bool(payload.get("use_latest_from_prefix", False), default=False)

        source_bucket: str | None = None
        source_prefix: str | None = None
        last_seen_key: str | None = None
        if use_latest_from_prefix:
            source_bucket = str(payload.get("source_bucket", "")).strip()
            source_prefix = str(payload.get("source_prefix", "")).strip()
            if not source_bucket or not source_prefix:
                raise ValueError(
                    "source_bucket and source_prefix are required when use_latest_from_prefix=true."
                )
            latest_record = get_latest_s3_object(
                bucket=source_bucket,
                prefix=source_prefix,
                suffix=".csv",
                s3_client=s3_client,
            )
            input_s3_uri = str(latest_record["uri"])
            seen_key = str(payload.get("last_seen_key", "")).strip()
            last_seen_key = seen_key or None
            if last_seen_key and str(latest_record["key"]) == last_seen_key:
                source_meta = {
                    "input_source": "s3",
                    "input_s3_uri": input_s3_uri,
                    "local_input_path": None,
                    "used_latest_from_prefix": True,
                    "latest_source_bucket": source_bucket,
                    "latest_source_prefix": source_prefix,
                    "latest_source_key": str(latest_record["key"]),
                    "last_seen_key": last_seen_key,
                    "no_new_data": True,
                }
                return None, source_meta
        else:
            latest_record = None
            input_s3_uri = str(payload.get("input_s3_uri", "")).strip()

        if use_latest_from_prefix:
            input_s3_uri = str(latest_record["uri"])
        if not input_s3_uri:
            raise ValueError("input_s3_uri is required when input_source='s3'.")
        parse_s3_uri(input_s3_uri)
        raw_df = read_csv_from_s3(input_s3_uri, s3_client)
        inference_df = load_inference_dataframe_from_dataframe(raw_df)
        source_meta = {
            "input_source": "s3",
            "input_s3_uri": input_s3_uri,
            "local_input_path": None,
            "used_latest_from_prefix": use_latest_from_prefix,
            "latest_source_bucket": source_bucket if use_latest_from_prefix else None,
            "latest_source_prefix": source_prefix if use_latest_from_prefix else None,
            "latest_source_key": str(latest_record["key"]) if latest_record else None,
            "last_seen_key": last_seen_key,
            "no_new_data": False,
        }
        return inference_df, source_meta

    local_input_path = str(payload.get("local_input_path", "")).strip()
    if not local_input_path:
        raise ValueError("local_input_path is required when input_source='local'.")

    resolved_local_path = resolve_project_path(local_input_path)
    inference_df = load_inference_dataframe(resolved_local_path)
    source_meta = {
        "input_source": "local",
        "input_s3_uri": None,
        "local_input_path": str(resolved_local_path),
        "used_latest_from_prefix": False,
        "latest_source_bucket": None,
        "latest_source_prefix": None,
        "latest_source_key": None,
        "last_seen_key": None,
        "no_new_data": False,
    }
    return inference_df, source_meta


def _run_selected_fusion(
    dataframe,
    fusion_method: str,
    threshold: float,
    model_artifact_path: Path | None,
):
    """Run soft-voting or logistic-stacking and return output dataframe."""

    if fusion_method == "soft_voting":
        engine = SoftVotingFusion(threat_threshold=threshold)
        return engine.predict(dataframe)

    if model_artifact_path is None:
        raise ValueError("Logistic stacking requires a model artifact path.")

    engine = LogisticFusionModel.load(model_artifact_path)
    return engine.predict(dataframe)


def _preview_records(dataframe, limit: int = 20) -> list[dict[str, Any]]:
    """Return JSON-safe preview rows for browser display."""

    preview_df = dataframe.head(limit).copy()
    for column in preview_df.columns:
        if column == "email_id":
            preview_df[column] = preview_df[column].astype(str)
    return json.loads(preview_df.to_json(orient="records"))


def create_app() -> Flask:
    """Create the Flask app used for local S3 testing."""

    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parents[1] / "web" / "templates"),
        static_folder=str(Path(__file__).resolve().parents[1] / "web" / "static"),
    )

    @app.get("/")
    def index():
        return render_template("index.html", supported_methods=SUPPORTED_FUSION_METHODS)

    @app.get("/api/health")
    def health_check():
        return jsonify({"ok": True, "status": "ready"})

    @app.post("/api/run-s3-fusion")
    def run_s3_fusion():
        payload = request.get_json(silent=True) or {}
        s3_client = boto3.client("s3")

        try:
            inference_df, source_meta = _load_input_dataframe(payload, s3_client)

            if source_meta.get("no_new_data"):
                return jsonify(
                    {
                        "ok": True,
                        "no_new_data": True,
                        "message": "No new S3 object since last_seen_key.",
                        "input_source": source_meta["input_source"],
                        "input_s3_uri": source_meta["input_s3_uri"],
                        "local_input_path": source_meta["local_input_path"],
                        "used_latest_from_prefix": source_meta["used_latest_from_prefix"],
                        "latest_source_bucket": source_meta["latest_source_bucket"],
                        "latest_source_prefix": source_meta["latest_source_prefix"],
                        "latest_source_key": source_meta["latest_source_key"],
                        "last_seen_key": source_meta["last_seen_key"],
                        "rows_scored": 0,
                        "preview": [],
                    }
                )

            fusion_method = str(payload.get("fusion_method", "logistic_regression_stacking")).strip()
            if fusion_method not in SUPPORTED_FUSION_METHODS:
                raise ValueError(
                    f"fusion_method must be one of {SUPPORTED_FUSION_METHODS}, got {fusion_method!r}."
                )

            config = load_config(None)
            threshold = float(config.get("thresholds", {}).get("final_label", 0.50))

            model_artifact_uri = str(payload.get("model_artifact_uri", "")).strip() or None
            artifact_path = _resolve_model_artifact_path(
                fusion_method=fusion_method,
                artifact_uri=model_artifact_uri,
                config=config,
                s3_client=s3_client,
            )

            predictions = _run_selected_fusion(
                dataframe=inference_df,
                fusion_method=fusion_method,
                threshold=threshold,
                model_artifact_path=artifact_path,
            )

            write_to_s3 = _coerce_bool(payload.get("write_output_to_s3", True), default=True)
            output_s3_uri: str | None = None
            if write_to_s3:
                explicit_output_uri = str(payload.get("output_s3_uri", "")).strip()
                if explicit_output_uri:
                    output_s3_uri = explicit_output_uri
                else:
                    if source_meta["input_source"] != "s3":
                        raise ValueError(
                            "output_s3_uri is required when input_source='local' and write_output_to_s3=true."
                        )
                    output_s3_uri = build_output_uri_from_input(
                        input_s3_uri=str(source_meta["input_s3_uri"]),
                        fusion_method=fusion_method,
                        output_bucket=str(payload.get("output_bucket", "")).strip() or None,
                        output_prefix=str(payload.get("output_prefix", "fusion-output")).strip()
                        or "fusion-output",
                        output_filename=str(payload.get("output_filename", "")).strip() or None,
                    )

            if write_to_s3:
                write_dataframe_to_s3_csv(predictions, str(output_s3_uri), s3_client)

            write_to_local = _coerce_bool(payload.get("write_output_local", False), default=False)
            local_output_path = str(payload.get("local_output_path", "")).strip()
            resolved_local_output_path: str | None = None
            if write_to_local or local_output_path:
                default_local_path = (
                    Path("artifacts") / f"web_app_{fusion_method}_predictions.csv"
                )
                resolved_local_output = write_output_dataframe(
                    predictions,
                    resolve_project_path(local_output_path) if local_output_path else default_local_path,
                )
                resolved_local_output_path = str(resolved_local_output)
                write_to_local = True

            return jsonify(
                {
                    "ok": True,
                    "fusion_method": fusion_method,
                    "rows_scored": int(len(predictions)),
                    "input_source": source_meta["input_source"],
                    "input_s3_uri": source_meta["input_s3_uri"],
                    "local_input_path": source_meta["local_input_path"],
                    "used_latest_from_prefix": source_meta["used_latest_from_prefix"],
                    "latest_source_bucket": source_meta["latest_source_bucket"],
                    "latest_source_prefix": source_meta["latest_source_prefix"],
                    "latest_source_key": source_meta["latest_source_key"],
                    "last_seen_key": source_meta["last_seen_key"],
                    "no_new_data": False,
                    "output_s3_uri": output_s3_uri,
                    "written_to_s3": write_to_s3,
                    "local_output_path": resolved_local_output_path,
                    "written_to_local": write_to_local,
                    "columns": list(predictions.columns),
                    "preview": _preview_records(predictions, limit=20),
                }
            )
        except Exception as exc:  # pragma: no cover - exercised via app flow
            return jsonify({"ok": False, "error": str(exc)}), 400

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
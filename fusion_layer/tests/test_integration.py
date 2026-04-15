"""Tests for integration-friendly branch assembly and end-to-end fusion execution."""

from __future__ import annotations

import json
import os

import pandas as pd

from src.integration import (
    assemble_fusion_input,
    normalize_branch_score_dataframe,
    run_integrated_fusion,
)


def test_normalize_branch_score_dataframe_infers_aliases() -> None:
    dataframe = pd.DataFrame(
        [
            {"message_id": "e1", "header_probability": 0.81},
            {"message_id": "e2", "header_probability": 0.12},
        ]
    )

    normalized = normalize_branch_score_dataframe(dataframe, model_name="header")

    assert list(normalized.columns) == ["email_id", "p_header"]
    assert normalized.to_dict(orient="records") == [
        {"email_id": "e1", "p_header": 0.81},
        {"email_id": "e2", "p_header": 0.12},
    ]


def test_normalize_branch_score_dataframe_uses_default_malware_max_strategy() -> None:
    dataframe = pd.DataFrame(
        [
            {"email_id": "e1", "attachment_score": 0.11},
            {"email_id": "e1", "attachment_score": 0.89},
            {"email_id": "e2", "attachment_score": 0.22},
        ]
    )

    normalized = normalize_branch_score_dataframe(dataframe, model_name="malware")

    assert normalized.to_dict(orient="records") == [
        {"email_id": "e1", "p_malware": 0.89},
        {"email_id": "e2", "p_malware": 0.22},
    ]


def test_assemble_fusion_input_outer_join_preserves_missing_modalities() -> None:
    header_scores = pd.DataFrame(
        [
            {"email_id": "e1", "p_header": 0.80},
            {"email_id": "e2", "p_header": 0.10},
        ]
    )
    body_scores = pd.DataFrame(
        [
            {"email_id": "e1", "p_body": 0.70},
            {"email_id": "e3", "p_body": 0.40},
        ]
    )

    assembled = assemble_fusion_input(header_scores=header_scores, body_scores=body_scores, join_type="outer")

    assert list(assembled.columns) == ["email_id", "p_header", "p_body", "p_malware"]
    assert assembled["email_id"].tolist() == ["e1", "e2", "e3"]
    assert pd.isna(assembled.loc[assembled["email_id"] == "e2", "p_body"]).all()
    assert pd.isna(assembled.loc[assembled["email_id"] == "e3", "p_header"]).all()


def test_run_integrated_fusion_local_end_to_end(tmp_path) -> None:
    header_input = tmp_path / "header_scores.csv"
    body_input = tmp_path / "body_scores.csv"
    malware_input = tmp_path / "malware_scores.csv"
    output_path = tmp_path / "integrated_predictions.csv"
    assembled_output_path = tmp_path / "assembled_input.csv"
    manifest_output_path = tmp_path / "manifest.json"

    header_input.write_text(
        "message_id,header_probability\n"
        "e1,0.88\n"
        "e2,0.14\n"
        "e3,0.49\n",
        encoding="utf-8",
    )
    body_input.write_text(
        "email_id,body_score\n"
        "e1,0.77\n"
        "e2,0.20\n"
        "e3,0.58\n",
        encoding="utf-8",
    )
    malware_input.write_text(
        "email_id,attachment_score\n"
        "e1,0.91\n"
        "e3,0.12\n"
        "e3,0.18\n",
        encoding="utf-8",
    )

    result = run_integrated_fusion(
        header_input=header_input,
        body_input=body_input,
        malware_input=malware_input,
        fusion_method="soft_voting",
        output_path=output_path,
        assembled_input_output=assembled_output_path,
        manifest_output=manifest_output_path,
    )

    assert output_path.exists()
    assert assembled_output_path.exists()
    assert manifest_output_path.exists()
    assert result.output_location == str(output_path)
    assert result.assembled_input_location == str(assembled_output_path)
    assert result.manifest_location == str(manifest_output_path)
    assert len(result.predictions) == 3
    assert result.predictions["fusion_method"].eq("soft_voting").all()
    assert result.assembled_input.loc[result.assembled_input["email_id"] == "e3", "p_malware"].iloc[0] == 0.18

    manifest = json.loads(manifest_output_path.read_text(encoding="utf-8"))
    assert manifest["rows_scored"] == 3
    assert manifest["duplicate_strategies"]["malware"] == "max"
    assert manifest["coverage"]["rows_with_malware"] == 2


def test_run_integrated_fusion_uses_configured_source_locations(tmp_path) -> None:
    config_path = tmp_path / "fusion_config.yaml"
    output_path = tmp_path / "configured_predictions.csv"

    header_input = tmp_path / "header_scores.csv"
    body_input = tmp_path / "body_scores.csv"
    malware_input = tmp_path / "malware_scores.csv"

    header_input.write_text(
        "message_id,header_probability\n"
        "e1,0.91\n"
        "e2,0.20\n",
        encoding="utf-8",
    )
    body_input.write_text(
        "email_id,body_score\n"
        "e1,0.80\n"
        "e2,0.31\n",
        encoding="utf-8",
    )
    malware_input.write_text(
        "email_id,attachment_score\n"
        "e1,0.95\n",
        encoding="utf-8",
    )

    config_path.write_text(
        "fusion:\n"
        "  primary_method: soft_voting\n"
        "thresholds:\n"
        "  final_label: 0.50\n"
        "  low_risk_max: 0.30\n"
        "  medium_risk_max: 0.70\n"
        "artifacts:\n"
        "  model_path: artifacts/logistic_fusion_model.joblib\n"
        "integration:\n"
        "  join_type: outer\n"
        "  sources:\n"
        f"    header:\n      location: {header_input}\n"
        f"    body:\n      location: {body_input}\n"
        f"    malware:\n      location: {malware_input}\n"
        "  duplicate_strategy:\n"
        "    header: error\n"
        "    body: error\n"
        "    malware: max\n",
        encoding="utf-8",
    )

    result = run_integrated_fusion(
        fusion_method="soft_voting",
        output_path=output_path,
        config_path=config_path,
    )

    assert output_path.exists()
    assert len(result.predictions) == 2
    assert result.manifest["sources"]["header"] == str(header_input)
    assert result.manifest["sources"]["body"] == str(body_input)
    assert result.manifest["sources"]["malware"] == str(malware_input)


def test_run_integrated_fusion_prefers_environment_source_locations(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "fusion_config.yaml"
    output_path = tmp_path / "env_predictions.csv"

    header_input = tmp_path / "header_scores.csv"
    body_input = tmp_path / "body_scores.csv"

    header_input.write_text(
        "message_id,header_probability\n"
        "e1,0.87\n",
        encoding="utf-8",
    )
    body_input.write_text(
        "email_id,body_score\n"
        "e1,0.52\n",
        encoding="utf-8",
    )

    config_path.write_text(
        "fusion:\n"
        "  primary_method: soft_voting\n"
        "thresholds:\n"
        "  final_label: 0.50\n"
        "  low_risk_max: 0.30\n"
        "  medium_risk_max: 0.70\n"
        "artifacts:\n"
        "  model_path: artifacts/logistic_fusion_model.joblib\n"
        "integration:\n"
        "  join_type: outer\n"
        "  sources:\n"
        "    header:\n      location: should_not_be_used.csv\n"
        "    body:\n      location: should_not_be_used_body.csv\n"
        "  duplicate_strategy:\n"
        "    header: error\n"
        "    body: error\n"
        "    malware: max\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("FUSION_HEADER_INPUT", str(header_input))
    monkeypatch.setenv("FUSION_BODY_INPUT", str(body_input))

    result = run_integrated_fusion(
        fusion_method="soft_voting",
        output_path=output_path,
        config_path=config_path,
    )

    assert output_path.exists()
    assert len(result.predictions) == 1
    assert result.manifest["sources"]["header"] == str(header_input)
    assert result.manifest["sources"]["body"] == str(body_input)


def test_run_integrated_fusion_raises_when_no_sources_resolve(tmp_path) -> None:
    config_path = tmp_path / "fusion_config.yaml"
    config_path.write_text(
        "fusion:\n"
        "  primary_method: soft_voting\n"
        "thresholds:\n"
        "  final_label: 0.50\n"
        "  low_risk_max: 0.30\n"
        "  medium_risk_max: 0.70\n"
        "artifacts:\n"
        "  model_path: artifacts/logistic_fusion_model.joblib\n"
        "integration:\n"
        "  join_type: outer\n",
        encoding="utf-8",
    )

    try:
        run_integrated_fusion(config_path=config_path)
        assert False, "Expected ValueError when no branch inputs resolve"
    except ValueError as exc:
        assert "No branch input sources were resolved" in str(exc)
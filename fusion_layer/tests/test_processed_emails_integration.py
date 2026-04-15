"""Tests for local processed_emails directory integration."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.processed_emails_integration import (
    ProcessedEmailEntry,
    discover_score_file_candidates,
    load_processed_emails_state,
    read_local_score_file,
    run_processed_emails_fusion,
    scan_processed_emails_directory,
)


@pytest.fixture
def sample_processed_emails_dir(tmp_path: Path) -> Path:
    """Create a sample processed_emails directory structure."""
    root = tmp_path / "processed_emails"
    root.mkdir()

    # Email 1: Complete with header, body, and malware scores
    email1 = root / "email-001"
    email1.mkdir()
    (email1 / "header_prediction.json").write_text(
        json.dumps({"model": "header", "probability": 0.82}),
        encoding="utf-8",
    )
    (email1 / "body_output.json").write_text(
        json.dumps({"p_body": 0.71}),
        encoding="utf-8",
    )
    (email1 / "malware_score.json").write_text(
        json.dumps({"malware_probability": 0.91}),
        encoding="utf-8",
    )

    # Email 2: Missing malware (no attachments)
    email2 = root / "email-002"
    email2.mkdir()
    (email2 / "header.json").write_text(
        json.dumps({"score": 0.15}),
        encoding="utf-8",
    )
    (email2 / "body.json").write_text(
        json.dumps({"prediction": 0.22}),
        encoding="utf-8",
    )

    # Email 3: CSV format with multiple columns
    email3 = root / "email-003"
    email3.mkdir()
    (email3 / "header_scores.csv").write_text(
        "email_id,header_probability,timestamp\n"
        "email-003,0.48,2024-01-01T00:00:00\n",
        encoding="utf-8",
    )
    (email3 / "body_scores.csv").write_text(
        "email_id,body_score\n"
        "email-003,0.59\n",
        encoding="utf-8",
    )

    # Email 4: Missing required body score
    email4 = root / "email-004"
    email4.mkdir()
    (email4 / "header.json").write_text(
        json.dumps({"probability": 0.77}),
        encoding="utf-8",
    )

    # Email 5: Text format
    email5 = root / "email-005"
    email5.mkdir()
    (email5 / "header_prediction.txt").write_text("0.33", encoding="utf-8")
    (email5 / "body_result.txt").write_text("0.44", encoding="utf-8")

    return root


def test_discover_score_file_candidates_json(sample_processed_emails_dir: Path) -> None:
    email_dir = sample_processed_emails_dir / "email-001"
    candidates = discover_score_file_candidates(email_dir, model_name="header")

    assert len(candidates) > 0
    assert any("header" in str(path).lower() for path in candidates)


def test_discover_score_file_candidates_with_ignored_files(sample_processed_emails_dir: Path) -> None:
    email_dir = sample_processed_emails_dir / "email-001"
    (email_dir / "fusion_output.json").write_text("{}", encoding="utf-8")

    candidates_without_ignore = discover_score_file_candidates(email_dir, model_name="header")
    candidates_with_ignore = discover_score_file_candidates(
        email_dir,
        model_name="header",
        ignored_filenames={"fusion_output.json"},
    )

    assert len(candidates_with_ignore) <= len(candidates_without_ignore)


def test_read_local_score_file_json(sample_processed_emails_dir: Path) -> None:
    email_dir = sample_processed_emails_dir / "email-001"
    header_file = email_dir / "header_prediction.json"

    probability = read_local_score_file(header_file, model_name="header", email_id="email-001")

    assert probability == 0.82


def test_read_local_score_file_csv(sample_processed_emails_dir: Path) -> None:
    email_dir = sample_processed_emails_dir / "email-003"
    header_file = email_dir / "header_scores.csv"

    probability = read_local_score_file(header_file, model_name="header", email_id="email-003")

    assert probability == 0.48


def test_read_local_score_file_txt(sample_processed_emails_dir: Path) -> None:
    email_dir = sample_processed_emails_dir / "email-005"
    header_file = email_dir / "header_prediction.txt"

    probability = read_local_score_file(header_file, model_name="header", email_id="email-005")

    assert probability == 0.33


def test_scan_processed_emails_directory_discovers_all_emails(sample_processed_emails_dir: Path) -> None:
    entries = scan_processed_emails_directory(
        processed_emails_root=sample_processed_emails_dir,
        incremental=False,
    )

    assert len(entries) == 5
    email_ids = {entry.email_id for entry in entries}
    assert email_ids == {"email-001", "email-002", "email-003", "email-004", "email-005"}


def test_scan_processed_emails_directory_marks_ready_and_skipped(sample_processed_emails_dir: Path) -> None:
    entries = scan_processed_emails_directory(
        processed_emails_root=sample_processed_emails_dir,
        required_models=("header", "body"),
        incremental=False,
    )

    ready_entries = [e for e in entries if e.status == "ready"]
    skipped_entries = [e for e in entries if e.status.startswith("skipped_")]

    assert len(ready_entries) >= 3  # email-001, email-002, email-003, email-005
    assert len(skipped_entries) >= 1  # email-004 missing body


def test_scan_processed_emails_directory_incremental_unchanged(sample_processed_emails_dir: Path, tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"

    # First run
    first_entries = scan_processed_emails_directory(
        processed_emails_root=sample_processed_emails_dir,
        incremental=True,
        state=None,
    )

    # Build state
    state_payload = {"processed_emails": {}}
    for entry in first_entries:
        if entry.status == "ready":
            state_payload["processed_emails"][entry.email_id] = {
                "directory": entry.directory,
                "signature": entry.signature,
                "status": "processed",
                "scores": entry.scores,
                "source_files": entry.source_files,
            }

    # Second run with state
    second_entries = scan_processed_emails_directory(
        processed_emails_root=sample_processed_emails_dir,
        incremental=True,
        state=state_payload,
    )

    unchanged_entries = [e for e in second_entries if e.status == "unchanged"]
    assert len(unchanged_entries) > 0


def test_load_processed_emails_state_creates_default(tmp_path: Path) -> None:
    state_path = tmp_path / "nonexistent_state.json"
    state = load_processed_emails_state(state_path)

    assert state == {"processed_emails": {}}


def test_load_processed_emails_state_loads_existing(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    existing_state = {
        "processed_emails": {
            "email-001": {"directory": "/path", "signature": "sig1", "status": "processed"}
        }
    }
    state_path.write_text(json.dumps(existing_state), encoding="utf-8")

    state = load_processed_emails_state(state_path)

    assert state == existing_state


def test_run_processed_emails_fusion_end_to_end(sample_processed_emails_dir: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "predictions.csv"
    manifest_path = tmp_path / "manifest.json"
    state_path = tmp_path / "state.json"

    result = run_processed_emails_fusion(
        processed_emails_root=sample_processed_emails_dir,
        fusion_method="soft_voting",
        output_path=output_path,
        manifest_output=manifest_path,
        state_path=state_path,
        incremental=True,
    )

    assert output_path.exists()
    assert manifest_path.exists()
    assert state_path.exists()
    assert len(result.predictions) >= 3
    assert result.predictions["fusion_method"].eq("soft_voting").all()
    assert result.state_location == str(state_path)


def test_run_processed_emails_fusion_incremental_no_new_data(sample_processed_emails_dir: Path, tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"

    # First run
    first_result = run_processed_emails_fusion(
        processed_emails_root=sample_processed_emails_dir,
        fusion_method="soft_voting",
        state_path=state_path,
        incremental=True,
    )

    first_count = len(first_result.predictions)

    # Second run - should have no new data
    second_result = run_processed_emails_fusion(
        processed_emails_root=sample_processed_emails_dir,
        fusion_method="soft_voting",
        state_path=state_path,
        incremental=True,
    )

    assert second_result.manifest["no_new_data"] is True
    assert len(second_result.predictions) == 0
    assert second_result.manifest["unchanged_email_directories"] == first_count


def test_run_processed_emails_fusion_writes_per_email_outputs(sample_processed_emails_dir: Path, tmp_path: Path) -> None:
    result = run_processed_emails_fusion(
        processed_emails_root=sample_processed_emails_dir,
        fusion_method="soft_voting",
        per_email_output_filename="test_output.json",
        incremental=False,
    )

    # Check that at least one email has the output file
    output_exists = False
    for entry in result.manifest["entries"]:
        if entry["status"] == "ready":
            email_dir = Path(entry["directory"])
            output_file = email_dir / "test_output.json"
            if output_file.exists():
                output_exists = True
                output_data = json.loads(output_file.read_text(encoding="utf-8"))
                assert "email_id" in output_data
                assert "final_score" in output_data
                assert "source_files" in output_data
                break

    assert output_exists
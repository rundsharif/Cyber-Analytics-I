"""Tests for risk-band mapping behavior."""

from __future__ import annotations

from src.risk_mapping import map_score_to_risk


def test_risk_mapping_boundaries() -> None:
    assert map_score_to_risk(0.00) == "low / benign"
    assert map_score_to_risk(0.299999) == "low / benign"
    assert map_score_to_risk(0.30) == "medium / suspicious"
    assert map_score_to_risk(0.699999) == "medium / suspicious"
    assert map_score_to_risk(0.70) == "high / malicious"
    assert map_score_to_risk(1.00) == "high / malicious"

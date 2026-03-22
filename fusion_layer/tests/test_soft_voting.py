"""Tests for the soft-voting baseline."""

from __future__ import annotations

import pandas as pd
import pytest

from src.soft_voting import SoftVotingFusion


def test_soft_voting_averages_only_present_modalities() -> None:
    df = pd.DataFrame(
        [
            {
                "email_id": "e-baseline",
                "p_header": 0.10,
                "p_body": 0.22,
                "p_malware": None,
            }
        ]
    )

    fusion = SoftVotingFusion(threat_threshold=0.50)
    output = fusion.predict(df)

    assert output.loc[0, "final_score"] == pytest.approx(0.16)
    assert output.loc[0, "final_label"] == 0
    assert output.loc[0, "risk_level"] == "low / benign"
    assert output.loc[0, "models_used"] == "header|body"
    assert output.loc[0, "fusion_method"] == "soft_voting"

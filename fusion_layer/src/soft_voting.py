"""Soft-voting baseline for late fusion."""

from __future__ import annotations

import pandas as pd

from src.contracts import MODEL_PROBABILITY_COLUMNS
from src.preprocess import annotate_model_availability
from src.utils import build_output_dataframe


class SoftVotingFusion:
    """Average available probabilities across present modalities only."""

    method_name = "soft_voting"

    def __init__(self, threat_threshold: float = 0.50) -> None:
        self.threat_threshold = float(threat_threshold)

    def predict_scores(self, inference_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        annotated = annotate_model_availability(inference_df)
        scores = annotated.loc[:, list(MODEL_PROBABILITY_COLUMNS)].mean(axis=1, skipna=True)
        return annotated, scores.astype(float)

    def predict(self, inference_df: pd.DataFrame) -> pd.DataFrame:
        annotated, scores = self.predict_scores(inference_df)
        return build_output_dataframe(
            source_df=annotated,
            scores=scores,
            fusion_method=self.method_name,
            threat_threshold=self.threat_threshold,
        )

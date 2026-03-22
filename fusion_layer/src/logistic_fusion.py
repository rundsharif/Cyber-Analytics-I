"""Logistic-regression stacking model for late fusion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.exceptions import NotFittedError
from sklearn.linear_model import LogisticRegression

from src.preprocess import LOGISTIC_FEATURE_COLUMNS, prepare_logistic_features
from src.utils import build_output_dataframe, ensure_parent_directory


class LogisticFusionModel:
    """Production-minded wrapper around logistic regression stacking."""

    method_name = "logistic_regression_stacking"

    def __init__(
        self,
        imputation_value: float = 0.50,
        threat_threshold: float = 0.50,
        C: float = 1.0,
        solver: str = "liblinear",
        max_iter: int = 1000,
        random_state: int = 42,
    ) -> None:
        self.imputation_value = float(imputation_value)
        self.threat_threshold = float(threat_threshold)
        self.feature_columns_ = list(LOGISTIC_FEATURE_COLUMNS)
        self.estimator = LogisticRegression(
            C=C,
            solver=solver,
            max_iter=max_iter,
            random_state=random_state,
        )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "LogisticFusionModel":
        """Create a model instance from YAML configuration."""

        preprocessing = config.get("preprocessing", {})
        thresholds = config.get("thresholds", {})
        logistic_config = config.get("logistic_regression", {})
        return cls(
            imputation_value=preprocessing.get("missing_probability_imputation", 0.50),
            threat_threshold=thresholds.get("final_label", 0.50),
            C=logistic_config.get("C", 1.0),
            solver=logistic_config.get("solver", "liblinear"),
            max_iter=logistic_config.get("max_iter", 1000),
            random_state=logistic_config.get("random_state", 42),
        )

    def _ensure_fitted(self) -> None:
        if not hasattr(self.estimator, "classes_"):
            raise NotFittedError("The logistic fusion model must be fitted before inference.")

    def fit(self, training_df: pd.DataFrame) -> "LogisticFusionModel":
        """Fit the stacking model on labeled fusion rows."""

        _, feature_frame = prepare_logistic_features(
            training_df,
            imputation_value=self.imputation_value,
        )
        target = training_df["true_label"].astype(int)
        self.estimator.fit(feature_frame[self.feature_columns_], target)
        return self

    def predict_scores(self, inference_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        """Return fused probabilities for an inference dataframe."""

        self._ensure_fitted()
        annotated, feature_frame = prepare_logistic_features(
            inference_df,
            imputation_value=self.imputation_value,
        )
        probabilities = self.estimator.predict_proba(feature_frame[self.feature_columns_])[:, 1]
        score_series = pd.Series(probabilities, index=inference_df.index, name="final_score")
        return annotated, score_series

    def predict(self, inference_df: pd.DataFrame) -> pd.DataFrame:
        """Return the fully formatted fusion output dataframe."""

        annotated, scores = self.predict_scores(inference_df)
        return build_output_dataframe(
            source_df=annotated,
            scores=scores,
            fusion_method=self.method_name,
            threat_threshold=self.threat_threshold,
        )

    def coefficients(self) -> dict[str, float]:
        """Return a readable mapping of feature names to coefficients."""

        self._ensure_fitted()
        return {
            feature_name: float(coefficient)
            for feature_name, coefficient in zip(self.feature_columns_, self.estimator.coef_[0])
        }

    def metadata(self, training_rows: int | None = None) -> dict[str, Any]:
        """Return explainability-friendly metadata for the trained model."""

        self._ensure_fitted()
        metadata = {
            "model_type": self.method_name,
            "imputation_value": self.imputation_value,
            "threat_threshold": self.threat_threshold,
            "feature_columns": self.feature_columns_,
            "coefficients": self.coefficients(),
            "intercept": float(self.estimator.intercept_[0]),
        }
        if training_rows is not None:
            metadata["training_rows"] = int(training_rows)
        return metadata

    def save(self, path: str | Path) -> Path:
        """Persist the trained model with joblib."""

        resolved_path = ensure_parent_directory(path)
        joblib.dump(self, resolved_path)
        return resolved_path

    @staticmethod
    def load(path: str | Path) -> "LogisticFusionModel":
        """Load a previously saved model artifact."""

        loaded = joblib.load(path)
        if not isinstance(loaded, LogisticFusionModel):
            raise TypeError("Loaded artifact is not a LogisticFusionModel instance.")
        return loaded

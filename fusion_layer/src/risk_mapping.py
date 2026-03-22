"""Risk-band mapping utilities for fusion scores."""

from __future__ import annotations

from typing import Iterable, List


def _validate_score(score: float) -> float:
    numeric = float(score)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"Score must be in [0.0, 1.0], got {numeric}.")
    return numeric


def map_score_to_risk(score: float) -> str:
    """Map a fusion probability to the required risk band.

    Boundaries are implemented as:
    - [0.00, 0.30) -> low / benign
    - [0.30, 0.70) -> medium / suspicious
    - [0.70, 1.00] -> high / malicious
    """

    numeric = _validate_score(score)
    if numeric < 0.30:
        return "low / benign"
    if numeric < 0.70:
        return "medium / suspicious"
    return "high / malicious"


def label_from_score(score: float, threshold: float = 0.50) -> int:
    """Convert a score to a binary label using a configurable threshold."""

    numeric = _validate_score(score)
    threshold = float(threshold)
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"Threshold must be in [0.0, 1.0], got {threshold}.")
    return int(numeric >= threshold)


def map_scores_to_risk(scores: Iterable[float]) -> List[str]:
    """Vector-friendly helper for applying risk mapping to multiple scores."""

    return [map_score_to_risk(score) for score in scores]

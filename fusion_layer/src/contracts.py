"""Strict row-level contracts for fusion inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Optional

MODEL_PROBABILITY_COLUMNS = ("p_header", "p_body", "p_malware")
TRAINING_INPUT_COLUMNS = ("email_id", *MODEL_PROBABILITY_COLUMNS, "true_label")
INFERENCE_INPUT_COLUMNS = ("email_id", *MODEL_PROBABILITY_COLUMNS)
OUTPUT_COLUMNS = (
    "email_id",
    "final_score",
    "final_label",
    "risk_level",
    "models_used",
    "fusion_method",
)

VALID_RISK_LEVELS = (
    "low / benign",
    "medium / suspicious",
    "high / malicious",
)


def _is_missing(value: object) -> bool:
    """Return True when a value should be treated as missing."""

    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _validate_email_id(email_id: object) -> str:
    if _is_missing(email_id):
        raise ValueError("email_id must be present.")
    cleaned = str(email_id).strip()
    if not cleaned:
        raise ValueError("email_id must be a non-empty string.")
    return cleaned


def _coerce_optional_probability(field_name: str, value: object) -> Optional[float]:
    if _is_missing(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a float in [0.0, 1.0] or blank.") from exc
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{field_name} must be within [0.0, 1.0].")
    return numeric


def _coerce_binary_label(field_name: str, value: object) -> int:
    if _is_missing(value):
        raise ValueError(f"{field_name} must be present.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be 0 or 1.") from exc
    if numeric not in (0.0, 1.0):
        raise ValueError(f"{field_name} must be 0 or 1.")
    return int(numeric)


@dataclass
class FusionInferenceRecord:
    """Contract for one inference row."""

    email_id: str
    p_header: Optional[float]
    p_body: Optional[float]
    p_malware: Optional[float]

    def __post_init__(self) -> None:
        self.email_id = _validate_email_id(self.email_id)
        self.p_header = _coerce_optional_probability("p_header", self.p_header)
        self.p_body = _coerce_optional_probability("p_body", self.p_body)
        self.p_malware = _coerce_optional_probability("p_malware", self.p_malware)
        if all(value is None for value in (self.p_header, self.p_body, self.p_malware)):
            raise ValueError("At least one model probability must be present.")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "FusionInferenceRecord":
        return cls(
            email_id=payload["email_id"],
            p_header=payload["p_header"],
            p_body=payload["p_body"],
            p_malware=payload["p_malware"],
        )


@dataclass
class FusionTrainingRecord(FusionInferenceRecord):
    """Contract for one labeled training row."""

    true_label: int

    def __post_init__(self) -> None:
        super().__post_init__()
        self.true_label = _coerce_binary_label("true_label", self.true_label)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "FusionTrainingRecord":
        return cls(
            email_id=payload["email_id"],
            p_header=payload["p_header"],
            p_body=payload["p_body"],
            p_malware=payload["p_malware"],
            true_label=payload["true_label"],
        )


@dataclass
class FusionOutputRecord:
    """Contract for one fusion output row."""

    email_id: str
    final_score: float
    final_label: int
    risk_level: str
    models_used: str
    fusion_method: str

    def __post_init__(self) -> None:
        self.email_id = _validate_email_id(self.email_id)
        self.final_score = _coerce_optional_probability("final_score", self.final_score)  # type: ignore[assignment]
        if self.final_score is None:
            raise ValueError("final_score must be present.")
        self.final_label = _coerce_binary_label("final_label", self.final_label)
        self.risk_level = str(self.risk_level).strip()
        if self.risk_level not in VALID_RISK_LEVELS:
            raise ValueError(
                f"risk_level must be one of {VALID_RISK_LEVELS}, got {self.risk_level!r}."
            )
        self.models_used = str(self.models_used).strip()
        if not self.models_used:
            raise ValueError("models_used must be present.")
        self.fusion_method = str(self.fusion_method).strip()
        if not self.fusion_method:
            raise ValueError("fusion_method must be present.")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "FusionOutputRecord":
        return cls(
            email_id=payload["email_id"],
            final_score=payload["final_score"],
            final_label=payload["final_label"],
            risk_level=payload["risk_level"],
            models_used=payload["models_used"],
            fusion_method=payload["fusion_method"],
        )

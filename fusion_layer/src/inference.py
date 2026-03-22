"""Inference CLI for fusion-layer predictions."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.loaders import load_inference_dataframe, write_output_dataframe
from src.logistic_fusion import LogisticFusionModel
from src.soft_voting import SoftVotingFusion
from src.utils import get_configured_artifact_path, get_project_root, load_config

SUPPORTED_FUSION_METHODS = ("soft_voting", "logistic_regression_stacking")


def run_inference(
    input_csv: str | Path,
    fusion_method: str | None = None,
    output_path: str | Path | None = None,
    config_path: str | Path | None = None,
    model_artifact: str | Path | None = None,
) -> tuple[Path, object]:
    """Run either soft-voting or logistic-stacking inference."""

    config = load_config(config_path)
    inference_df = load_inference_dataframe(input_csv)
    method = fusion_method or config.get("fusion", {}).get("primary_method", "logistic_regression_stacking")

    if method not in SUPPORTED_FUSION_METHODS:
        raise ValueError(f"fusion_method must be one of {SUPPORTED_FUSION_METHODS}, got {method!r}.")

    threshold = config.get("thresholds", {}).get("final_label", 0.50)
    if method == "soft_voting":
        fusion_engine = SoftVotingFusion(threat_threshold=threshold)
        predictions = fusion_engine.predict(inference_df)
    else:
        artifact_path = Path(model_artifact) if model_artifact else get_configured_artifact_path(config, "model_path")
        fusion_engine = LogisticFusionModel.load(artifact_path)
        predictions = fusion_engine.predict(inference_df)

    resolved_output = (
        Path(output_path)
        if output_path
        else get_project_root() / "artifacts" / f"{method}_predictions.csv"
    )
    output_csv = write_output_dataframe(predictions, resolved_output)
    return output_csv, predictions


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fusion inference on model probability CSVs.")
    parser.add_argument("--input", required=True, help="Path to the fusion inference CSV.")
    parser.add_argument(
        "--fusion-method",
        default=None,
        choices=SUPPORTED_FUSION_METHODS,
        help="Fusion method to run. Defaults to the configured primary method.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path for the prediction CSV.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional path to a YAML config file. Defaults to config/fusion_config.yaml.",
    )
    parser.add_argument(
        "--model-artifact",
        default=None,
        help="Optional joblib model path for logistic stacking inference.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    output_csv, predictions = run_inference(
        input_csv=args.input,
        fusion_method=args.fusion_method,
        output_path=args.output,
        config_path=args.config,
        model_artifact=args.model_artifact,
    )

    print("Fusion inference complete.")
    print(f"Predictions written to: {output_csv}")
    print(f"Rows scored: {len(predictions)}")
    display_df = predictions.copy()
    if "final_score" in display_df.columns:
        display_df["final_score"] = display_df["final_score"].map(lambda value: round(float(value), 6))
    print("\nPrediction scores:")
    print(display_df.to_string(index=False))


if __name__ == "__main__":
    main()

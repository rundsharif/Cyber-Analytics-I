"""Training CLI for the logistic regression fusion model."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.loaders import load_training_dataframe
from src.logistic_fusion import LogisticFusionModel
from src.utils import get_configured_artifact_path, load_config, save_json


def train_fusion_model(
    input_csv: str | Path,
    config_path: str | Path | None = None,
    model_output: str | Path | None = None,
    metadata_output: str | Path | None = None,
) -> tuple[Path, Path, dict]:
    """Train the logistic regression stacking model and save its artifacts."""

    config = load_config(config_path)
    training_df = load_training_dataframe(input_csv)
    model = LogisticFusionModel.from_config(config)
    model.fit(training_df)

    model_path = Path(model_output) if model_output else get_configured_artifact_path(config, "model_path")
    metadata_path = (
        Path(metadata_output)
        if metadata_output
        else get_configured_artifact_path(config, "metadata_path")
    )

    model.save(model_path)
    metadata = model.metadata(training_rows=len(training_df))
    save_json(metadata, metadata_path)
    return model_path, metadata_path, metadata


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the logistic regression fusion model.")
    parser.add_argument("--input", required=True, help="Path to the labeled fusion training CSV.")
    parser.add_argument(
        "--config",
        default=None,
        help="Optional path to a YAML config file. Defaults to config/fusion_config.yaml.",
    )
    parser.add_argument(
        "--model-output",
        default=None,
        help="Optional output path for the joblib model artifact.",
    )
    parser.add_argument(
        "--metadata-output",
        default=None,
        help="Optional output path for the JSON metadata artifact.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    model_path, metadata_path, metadata = train_fusion_model(
        input_csv=args.input,
        config_path=args.config,
        model_output=args.model_output,
        metadata_output=args.metadata_output,
    )

    print("Fusion model training complete.")
    print(f"Model artifact saved to: {model_path}")
    print(f"Metadata artifact saved to: {metadata_path}")
    print(f"Training rows: {metadata.get('training_rows')}")
    print(f"Feature columns: {', '.join(metadata.get('feature_columns', []))}")


if __name__ == "__main__":
    main()

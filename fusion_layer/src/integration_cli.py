"""CLI for integration-friendly branch-score assembly and fusion execution."""

from __future__ import annotations

import argparse

from src.integration import SUPPORTED_DUPLICATE_STRATEGIES, SUPPORTED_JOIN_TYPES, run_integrated_fusion
from src.processed_emails_integration import run_processed_emails_fusion


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble header/body/malware branch score CSVs into canonical fusion input and "
            "run the fusion layer end-to-end. If the three branch inputs are omitted here, "
            "the CLI will resolve them from environment variables or config/fusion_config.yaml."
        )
    )

    parser.add_argument("--header-input", default=None, help="Local path or S3 URI for header-model scores.")
    parser.add_argument("--body-input", default=None, help="Local path or S3 URI for body-model scores.")
    parser.add_argument("--malware-input", default=None, help="Local path or S3 URI for malware-model scores.")

    parser.add_argument("--header-email-id-column", default=None)
    parser.add_argument("--header-score-column", default=None)
    parser.add_argument("--body-email-id-column", default=None)
    parser.add_argument("--body-score-column", default=None)
    parser.add_argument("--malware-email-id-column", default=None)
    parser.add_argument("--malware-score-column", default=None)

    parser.add_argument(
        "--header-duplicate-strategy",
        choices=SUPPORTED_DUPLICATE_STRATEGIES,
        default=None,
        help="How to handle duplicate email IDs in the header branch.",
    )
    parser.add_argument(
        "--body-duplicate-strategy",
        choices=SUPPORTED_DUPLICATE_STRATEGIES,
        default=None,
        help="How to handle duplicate email IDs in the body branch.",
    )
    parser.add_argument(
        "--malware-duplicate-strategy",
        choices=SUPPORTED_DUPLICATE_STRATEGIES,
        default=None,
        help="How to handle duplicate email IDs in the malware branch.",
    )

    parser.add_argument(
        "--join-type",
        choices=SUPPORTED_JOIN_TYPES,
        default=None,
        help="How branch scoreframes should be joined by email_id.",
    )
    parser.add_argument(
        "--fusion-method",
        default=None,
        choices=("soft_voting", "logistic_regression_stacking"),
        help="Fusion method to run. Defaults to the configured primary method.",
    )
    parser.add_argument("--output", default=None, help="Destination for final fused predictions (local path or S3 URI).")
    parser.add_argument(
        "--assembled-input-output",
        default=None,
        help="Optional destination to write the assembled canonical fusion input CSV.",
    )
    parser.add_argument(
        "--manifest-output",
        default=None,
        help="Optional destination for the integration manifest JSON.",
    )
    parser.add_argument("--config", default=None, help="Optional fusion config YAML path.")
    parser.add_argument("--model-artifact", default=None, help="Optional local path or S3 URI to logistic artifact.")

    parser.add_argument(
        "--processed-emails-root",
        default=None,
        help=(
            "Local processed_emails directory root. When provided, the CLI scans per-email UUID "
            "directories locally instead of expecting separate branch score CSV inputs."
        ),
    )
    parser.add_argument(
        "--state-path",
        default=None,
        help="Optional local JSON state file used for incremental processed_emails runs.",
    )
    parser.add_argument(
        "--per-email-output-filename",
        default=None,
        help="Optional filename to write inside each processed email directory for final fusion output JSON.",
    )
    parser.add_argument(
        "--no-incremental",
        action="store_true",
        help="Disable incremental state filtering for processed_emails directory runs.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.processed_emails_root:
        result = run_processed_emails_fusion(
            processed_emails_root=args.processed_emails_root,
            fusion_method=args.fusion_method,
            output_path=args.output,
            assembled_input_output=args.assembled_input_output,
            manifest_output=args.manifest_output,
            state_path=args.state_path,
            config_path=args.config,
            model_artifact=args.model_artifact,
            per_email_output_filename=args.per_email_output_filename
            if args.per_email_output_filename
            else None,
            incremental=not args.no_incremental,
        )
    else:
        result = run_integrated_fusion(
            header_input=args.header_input,
            body_input=args.body_input,
            malware_input=args.malware_input,
            fusion_method=args.fusion_method,
            output_path=args.output,
            assembled_input_output=args.assembled_input_output,
            manifest_output=args.manifest_output,
            config_path=args.config,
            model_artifact=args.model_artifact,
            header_email_id_column=args.header_email_id_column,
            header_score_column=args.header_score_column,
            body_email_id_column=args.body_email_id_column,
            body_score_column=args.body_score_column,
            malware_email_id_column=args.malware_email_id_column,
            malware_score_column=args.malware_score_column,
            header_duplicate_strategy=args.header_duplicate_strategy,
            body_duplicate_strategy=args.body_duplicate_strategy,
            malware_duplicate_strategy=args.malware_duplicate_strategy,
            join_type=args.join_type,
        )

    print("Integrated fusion complete.")
    print(f"Rows scored: {len(result.predictions)}")
    if result.output_location:
        print(f"Predictions written to: {result.output_location}")
    if result.assembled_input_location:
        print(f"Assembled fusion input written to: {result.assembled_input_location}")
    if result.manifest_location:
        print(f"Manifest written to: {result.manifest_location}")
    if getattr(result, "state_location", None):
        print(f"State written to: {result.state_location}")

    preview = result.predictions.copy()
    if "final_score" in preview.columns:
        preview["final_score"] = preview["final_score"].map(lambda value: round(float(value), 6))
    print("\nPrediction preview:")
    print(preview.to_string(index=False))


if __name__ == "__main__":
    main()
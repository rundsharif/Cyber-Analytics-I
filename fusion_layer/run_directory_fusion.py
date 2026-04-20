#!/usr/bin/env python3
"""Run fusion on directory-based model outputs.

This script is designed for the directory structure where each model
outputs one JSON file per email UUID:
    /home/hhj689_local/Documents/model_outputs/
    ├── header/
    │   └── {uuid}.json
    ├── body/
    │   └── {uuid}.json
    └── malware/
        └── {uuid}.json
"""

import sys
from pathlib import Path

from src.processed_emails_integration import run_processed_emails_fusion


def main():
    # Configuration
    MODEL_OUTPUTS_DIR = "/home/hhj689_local/Documents/model_outputs"
    OUTPUT_CSV = "/home/hhj689_local/Documents/model_outputs/fusion_predictions.csv"
    STATE_FILE = "/home/hhj689_local/Documents/model_outputs/fusion_state.json"
    
    # You can override these from command line
    if len(sys.argv) > 1:
        MODEL_OUTPUTS_DIR = sys.argv[1]
    if len(sys.argv) > 2:
        OUTPUT_CSV = sys.argv[2]
    
    # Derive state file from the model outputs directory
    STATE_FILE = str(Path(MODEL_OUTPUTS_DIR) / "fusion_state.json")
    
    print(f"Running fusion on directory: {MODEL_OUTPUTS_DIR}")
    print(f"Output will be written to: {OUTPUT_CSV}")
    print()
    
    try:
        result = run_processed_emails_fusion(
            processed_emails_root=MODEL_OUTPUTS_DIR,
            fusion_method="logistic_regression_stacking",
            output_path=OUTPUT_CSV,
            incremental=True,  # Only process new/changed emails
            state_path=STATE_FILE,
        )
        
        print("=" * 60)
        print("FUSION COMPLETE")
        print("=" * 60)
        print(f"✓ Processed {len(result.predictions)} emails")
        print(f"✓ Predictions: {result.output_location}")
        print(f"✓ Manifest: {result.manifest_location}")
        print(f"✓ State saved: {result.state_location}")
        print()
        
        # Show preview of results
        print("Preview of predictions:")
        print(result.predictions.head(10).to_string(index=False))
        print()
        
        # Show summary statistics
        print("Risk level distribution:")
        print(result.predictions['risk_level'].value_counts().to_string())
        
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print()
        print("Make sure the model output directory exists and contains:")
        print("  - header/ subdirectory with {uuid}.json files")
        print("  - body/ subdirectory with {uuid}.json files")
        print("  - malware/ subdirectory with {uuid}.json files (for emails with attachments)")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

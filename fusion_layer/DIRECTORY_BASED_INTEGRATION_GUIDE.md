# Directory-Based Integration Guide

## Your Setup

**Model Output Directory:** `/home/hhj689_local/Documents/model_outputs`

**Directory Structure (Organized by Email UUID):**
```
/home/hhj689_local/Documents/model_outputs/
├── 5b297a3f-a732-4aff-976b-d2b8af69c610/
│   ├── header.json
│   ├── body.json
│   └── malware.json (if attachment exists)
├── 7c9e6679-7425-40de-944b-e07fc1f90ae7/
│   ├── header.json
│   ├── body.json
│   └── (no malware.json - no attachment)
└── ... (one subdirectory per email UUID)
```

**Important:** Each email gets its own subdirectory named after its UUID, containing the model outputs for that email.

## JSON File Format

Each model outputs JSON files with this structure:

**Header model** - `/home/hhj689_local/Documents/model_outputs/{uuid}/header.json`:
```json
{"email_id": "5b297a3f-a732-4aff-976b-d2b8af69c610", "probability_header": 0.88}
```

**Body model** - `/home/hhj689_local/Documents/model_outputs/{uuid}/body.json`:
```json
{"email_id": "5b297a3f-a732-4aff-976b-d2b8af69c610", "probability_body": 0.77}
```

**Malware model** - `/home/hhj689_local/Documents/model_outputs/{uuid}/malware.json`:
```json
{"email_id": "5b297a3f-a732-4aff-976b-d2b8af69c610", "probability_malicious": 0.91}
```

**Note:** The JSON key names are flexible - the fusion layer will auto-detect fields like `probability`, `score`, `probability_header`, `probability_malicious`, etc.

## How to Run Fusion Layer

### Step 1: Create a Python script

Create `run_directory_fusion.py`:

```python
#!/usr/bin/env python3
"""Run fusion on directory-based model outputs."""

from src.processed_emails_integration import run_processed_emails_fusion

# Run fusion on your model output directory
result = run_processed_emails_fusion(
    processed_emails_root="/home/hhj689_local/Documents/model_outputs",
    fusion_method="logistic_regression_stacking",
    output_path="/home/hhj689_local/Documents/model_outputs/fusion_predictions.csv"
)

print(f"✓ Processed {len(result.predictions)} emails")
print(f"✓ Predictions: {result.output_location}")
print(f"✓ Manifest: {result.manifest_location}")
print(f"✓ State saved: {result.state_location}")
```

### Step 2: Run it

```bash
python3 run_directory_fusion.py
```

## How the Fusion Layer Works

1. **Scans the directory** for email subdirectories or JSON files
2. **Auto-detects** which files are header/body/malware based on:
   - Filename (e.g., `header.json`, `body_score.json`)
   - Content (looks for `probability_header`, `probability_body`, etc.)
3. **Extracts probabilities** from each JSON file
4. **Merges** the three scores by UUID
5. **Runs fusion** (logistic regression stacking)
6. **Outputs** final predictions CSV

## Output Format

`/home/hhj689_local/Documents/model_outputs/fusion_predictions.csv`:
```csv
email_id,final_score,final_label,risk_level,models_used,fusion_method
5b297a3f-a732-4aff-976b-d2b8af69c610,0.876,1,high,header|body|malware,logistic_regression_stacking
7c9e6679-7425-40de-944b-e07fc1f90ae7,0.170,0,low,header|body,logistic_regression_stacking
```

## Incremental Processing

The fusion layer tracks which emails have been processed in a state file. On subsequent runs, it only processes **new or changed** emails.

To enable:
```python
result = run_processed_emails_fusion(
    processed_emails_root="/home/hhj689_local/Documents/model_outputs",
    incremental=True,
    state_path="/home/hhj689_local/Documents/model_outputs/fusion_state.json"
)
```

## Missing Data Handling

- If an email has no attachment → **no malware score** → fusion layer uses header + body only
- If header or body is missing → **email is skipped** (configurable)

## Configuration

Edit `config/fusion_config.yaml` for advanced settings:

```yaml
integration:
  processed_emails:
    incremental: true
    state_path: /home/hhj689_local/Documents/model_outputs/fusion_state.json
    required_models:  # Must have these models to process an email
      - header
      - body
    per_email_output_filename: fusion_output.json  # Optional: write results back to each email dir
```

## Troubleshooting

**Problem:** "Could not find score files for email {uuid}"
- Check that JSON files are named with keywords like `header`, `body`, or `malware`
- Verify the JSON contains recognizable score keys

**Problem:** "Email skipped - missing required models"
- Some emails may not have all required scores
- Adjust `required_models` in config if body-only or header-only emails are acceptable

**Problem:** "Could not parse probability from JSON"
- Ensure JSON contains numeric values between 0.0 and 1.0
- Fusion layer looks for keys like: `probability`, `score`, `prediction`, `probability_header`, etc.

## Performance

- Typical processing: **100-1000 emails/second**
- Incremental mode only processes new/changed emails
- State file prevents reprocessing on subsequent runs

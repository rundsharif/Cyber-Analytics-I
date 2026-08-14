# Fusion Layer — Integration Instructions
**Updated:** April 2026 | **Status: VERIFIED & READY**

---

## System Health Check (Verified ✓)

| Check | Status |
|-------|--------|
| All 32 unit tests | ✅ PASS |
| Trained model loads | ✅ PASS |
| End-to-end pipeline | ✅ PASS |
| JSON input parsing | ✅ PASS |
| Missing data handling | ✅ PASS |

---

## Overview

The fusion layer sits at the **end of the pipeline**, after the three upstream models have already scored each email. It reads their JSON output files, combines the scores, and produces a single final threat decision per email.

```
Upstream Models                    Fusion Layer                  Output
─────────────────────────────      ────────────────────────      ──────────────────────
Email → Header Model → .json  ─┐
Email → Body Model   → .json  ─┼─→  run_directory_fusion.py  →  fusion_predictions.csv
Email → Malware Model→ .json  ─┘
```

---

## What Your Teammates Need to Do (Upstream Models)

### Required Directory Structure

Each processed email must have its own subdirectory named after its UUID:

```
/home/hhj689_local/Documents/model_outputs/
├── 5b297a3f-a732-4aff-976b-d2b8af69c610/
│   ├── header.json        ← header model output
│   ├── body.json          ← body model output
│   └── malware.json       ← malware model output (only if attachment exists)
│
├── 7c9e6679-7425-40de-944b-e07fc1f90ae7/
│   ├── header.json
│   └── body.json          ← no malware.json (no attachment — that's fine!)
│
└── {next-uuid}/
    └── ...
```

### Required JSON Format

Each model outputs one JSON file per email containing the UUID and probability score:

**header.json:**
```json
{"email_id": "5b297a3f-a732-4aff-976b-d2b8af69c610", "probability_header": 0.88}
```

**body.json:**
```json
{"email_id": "5b297a3f-a732-4aff-976b-d2b8af69c610", "probability_body": 0.77}
```

**malware.json:** *(only create this file if the email has an attachment)*
```json
{"email_id": "5b297a3f-a732-4aff-976b-d2b8af69c610", "probability_malicious": 0.91}
```

### Flexible Key Names

The JSON key names are flexible — the fusion layer auto-detects them. Any of these will work:

| Model | Accepted key names |
|-------|--------------------|
| Header | `probability_header`, `header_score`, `score`, `probability`, `prediction` |
| Body | `probability_body`, `body_score`, `score`, `probability`, `prediction` |
| Malware | `probability_malicious`, `malware_score`, `score`, `probability`, `prediction` |

**File names** must contain `header`, `body`, or `malware` as a substring.

---

## How to Run the Fusion Layer

### Step 1: Pull from GitHub (First time — clone; after that — pull)

**First time on a new machine:**
```bash
git clone git@github.com:rundsharif/Cyber-Analytics-I.git
cd Cyber-Analytics-I/fusion_layer
```

**Already cloned — just get latest changes:**
```bash
cd Cyber-Analytics-I/fusion_layer
git pull origin main
```

### Step 2: Install Dependencies (First time only)

```bash
pip install -r requirements.txt
```

Or use the install script:
```bash
bash install_dependencies.sh
```

### Step 3: Run Fusion

**Default run (uses `/home/hhj689_local/Documents/model_outputs`):**
```bash
python3 run_directory_fusion.py
```

**Custom directory:**
```bash
python3 run_directory_fusion.py /path/to/model_outputs /path/to/output.csv
```

**Example output:**
```
Running fusion on directory: /home/hhj689_local/Documents/model_outputs
Output will be written to: /home/hhj689_local/Documents/model_outputs/fusion_predictions.csv

============================================================
FUSION COMPLETE
============================================================
✓ Processed 2 emails
✓ Predictions: /home/hhj689_local/Documents/model_outputs/fusion_predictions.csv
✓ Manifest: artifacts/processed_emails_logistic_regression_stacking_manifest.json
✓ State saved: /home/hhj689_local/Documents/model_outputs/fusion_state.json

Preview of predictions:
email_id                               final_score  final_label  risk_level
5b297a3f-a732-4aff-976b-d2b8af69c610  0.628        1            medium / suspicious
7c9e6679-7425-40de-944b-e07fc1f90ae7  0.372        0            medium / suspicious
```

### Step 4: Check Output

```bash
cat /home/hhj689_local/Documents/model_outputs/fusion_predictions.csv
```

---

## Output Format

The fusion layer produces a CSV with one row per email:

```csv
email_id,final_score,final_label,risk_level,models_used,fusion_method
5b297a3f-a732-4aff-976b-d2b8af69c610,0.628,1,medium / suspicious,header|body,logistic_regression_stacking
7c9e6679-7425-40de-944b-e07fc1f90ae7,0.372,0,medium / suspicious,header|body,logistic_regression_stacking
```

| Column | Type | Description |
|--------|------|-------------|
| `email_id` | string (UUID) | Email identifier |
| `final_score` | float (0.0-1.0) | Probability of being malicious |
| `final_label` | int (0 or 1) | 0=Benign, 1=Malicious |
| `risk_level` | string | `low / benign`, `medium / suspicious`, `high / malicious` |
| `models_used` | string | Pipe-separated models that contributed (e.g., `header\|body`) |
| `fusion_method` | string | `logistic_regression_stacking` or `soft_voting` |

### Risk Level Thresholds

| Score Range | Label | Risk Level |
|------------|-------|------------|
| 0.00 – 0.29 | 0 (Benign) | `low / benign` |
| 0.30 – 0.69 | 1 (Malicious) if ≥ 0.50 | `medium / suspicious` |
| 0.70 – 1.00 | 1 (Malicious) | `high / malicious` |

---

## How Missing Data is Handled

**The fusion layer is designed for the reality that malware scores will often be missing** (emails without attachments).

| Situation | What Happens |
|-----------|-------------|
| No malware score | Uses 0.5 (neutral) + sets `has_malware=0` flag |
| All three scores present | Full fusion across all 3 models |
| Only header + body | Fusion across 2 models (most common case) |
| Missing header OR body | Email is **skipped** (requires both header and body minimum) |
| Malformed JSON | Error logged, email skipped, processing continues |

---

## How the Fusion Algorithm Works

### Primary Method: Logistic Regression Stacking

**Step 1: Feature engineering** — Creates 7 features from the 3 scores:
```
Features = [p_header, p_body, p_malware, has_header, has_body, has_malware, count]
           (filled with 0.5 if missing)
```

**Step 2: Apply trained weights:**
```
logit = -0.261
      + (0.881 × p_header)     ← Header analysis most predictive
      + (0.692 × p_body)       ← Body analysis
      + (0.376 × p_malware)    ← Malware analysis
      + (-0.261 × has_header)  ← Confidence adjustment
      + (-0.261 × has_body)    ← Confidence adjustment
      + (0.426 × has_malware)  ← Attachment presence concern
      + (-0.095 × count)       ← Number of models adjustment
```

**Step 3: Sigmoid to probability:**
```
final_score = 1 / (1 + e^(-logit))
```

**Step 4: Threshold and classify:**
```
final_label = 1 if final_score >= 0.50 else 0
risk_level = map_to_band(final_score)
```

### Baseline Method: Soft Voting

A simple average for comparison:
```
final_score = average(available scores)
```

Run with `--method soft_voting` if needed.

---

## Incremental Processing

The fusion layer tracks which emails it has already processed in a **state file**. On repeated runs, it only processes new or changed emails.

**First run:** Processes all emails in the directory  
**Subsequent runs:** Only processes emails added or modified since last run  

To **force reprocess all emails**, delete the state file:
```bash
rm /home/hhj689_local/Documents/model_outputs/fusion_state.json
```

---

## Configuration

All settings are in `config/fusion_config.yaml`:

```yaml
fusion:
  primary_method: logistic_regression_stacking
  baseline_method: soft_voting

thresholds:
  final_label: 0.50          # Threshold for malicious classification
  low_risk_max: 0.30         # Upper bound for "low" risk
  medium_risk_max: 0.70      # Upper bound for "medium" risk

preprocessing:
  missing_probability_imputation: 0.50   # Value to fill missing scores with
  require_at_least_one_modality: true

artifacts:
  model_path: artifacts/logistic_fusion_model.joblib
  metadata_path: artifacts/logistic_fusion_metadata.json

integration:
  processed_emails:
    incremental: true
    required_models:        # Emails MUST have these or get skipped
      - header
      - body
    # malware is optional (common - not all emails have attachments)
```

---

## Troubleshooting

### "Processed 0 emails"
→ State file exists, all emails already marked as processed.  
**Fix:** Delete state file and re-run.
```bash
rm /path/to/model_outputs/fusion_state.json
python3 run_directory_fusion.py
```

### "Email skipped — missing required models"
→ Email directory is missing `header.json` or `body.json`.  
**Fix:** Ensure both header and body models have run for that email.

### "Could not parse probability from JSON"
→ JSON content doesn't have a recognizable numeric score key.  
**Fix:** Check JSON structure. Score must be a float between 0.0 and 1.0.

### "FileNotFoundError: artifacts/logistic_fusion_model.joblib"
→ Trained model file is missing.  
**Fix:** Retrain the model:
```bash
python3 train_fusion.py
```

### JSON file exists but score not detected
→ File name doesn't contain `header`, `body`, or `malware`.  
**Fix:** Rename files to include one of these keywords.

---

## File Reference

| File | Purpose |
|------|---------|
| `run_directory_fusion.py` | **Main script — run this for production use** |
| `train_fusion.py` | Retrain the fusion model with new labeled data |
| `run_inference.py` | Run inference from a CSV file instead of directory |
| `artifacts/logistic_fusion_model.joblib` | Trained model weights (do not delete) |
| `artifacts/logistic_fusion_metadata.json` | Human-readable model coefficients |
| `config/fusion_config.yaml` | All configuration settings |
| `src/logistic_fusion.py` | Core scoring algorithm (line 80) |
| `src/preprocess.py` | Feature engineering & missing data handling |
| `src/risk_mapping.py` | Risk level thresholds |
| `data/example_emails_by_uuid/` | Working example with 2 test emails |

---

## Quick Start Checklist for Teammates

**Header/Body/Malware model teammates:**
- [ ] Run your model on each email
- [ ] Save output as JSON: `{"email_id": "{uuid}", "probability_{type}": {score}}`
- [ ] Place in `/home/hhj689_local/Documents/model_outputs/{uuid}/{type}.json`
- [ ] Notify Seth when a batch is ready

**Seth (Fusion layer):**
- [ ] `cd /path/to/fusion_layer`
- [ ] `python3 run_directory_fusion.py`
- [ ] Share `fusion_predictions.csv` with team

---

## Verified Test Run Output

```
✓ 32/32 unit tests pass
✓ Model loads: logistic_regression_stacking (10 training rows)
✓ Weights: header=0.881, body=0.692, malware=0.376
✓ End-to-end: 2 test emails processed correctly
✓ UUID format: 5b297a3f-a732-4aff-976b-d2b8af69c610 → score=0.628, MALICIOUS, MEDIUM
✓ Missing malware handled correctly (header|body only)
```

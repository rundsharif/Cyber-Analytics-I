# Fusion Model Documentation

## 1. Purpose

This document describes the fusion model implemented in the `fusion_layer` project for the Cyber Analytics system. The fusion layer is the final decision stage that combines the outputs of the three specialized analysis branches:

- header branch
- body branch
- malware / attachment branch

Each branch produces a probability score representing how likely an email is to be malicious. The fusion layer combines those probabilities into a single final threat score and decision. This allows the overall system to remain modular while still producing one explainable result for downstream use in dashboards, APIs, or SOC workflows.

This model begins after preprocessing and after the branch models have already produced their outputs. It does not perform ingestion, parsing, or base-model feature extraction. Its role is strictly late fusion.

---

## 2. Position in the Full System

The full system flow is:

1. email ingestion
2. raw storage and preprocessing
3. branch-specific analysis
4. branch probability generation
5. fusion layer scoring
6. final threat output

In the current architecture, the fusion layer expects the upstream system to provide branch-level probabilities in a structured format. It is intentionally isolated from the ingestion pipeline so that it can be maintained, tested, and improved independently of the rest of the system.

---

## 3. Fusion Strategy

This project uses **late fusion**, which means the specialized models are trained independently and their outputs are combined only after each model has produced a prediction. This was chosen because it is easier to debug, easier to explain, easier to integrate across different data types, and more appropriate for the Phase 1 project scope than end-to-end neural fusion.

The fusion layer currently implements two methods:

### Primary method: logistic regression stacking

This is the main fusion model used for final scoring. It learns how to weight the branch outputs based on training data.

### Baseline method: soft voting

This provides a simple comparison method by averaging available probabilities. It is useful for benchmarking and for demonstrating the value of the learned fusion model.

---

## 4. Input Contract

The fusion model expects a per-email record with the following fields:

```json
{
  "email_id": "abc123",
  "p_header": 0.81,
  "p_body": 0.67,
  "p_malware": 0.92
}
```

Missing malware values are supported and expected for emails without attachments:

```json
{
  "email_id": "abc123",
  "p_header": 0.81,
  "p_body": 0.67,
  "p_malware": null
}
```

### Required rules

- `email_id` must be present and non-empty
- probability fields must be within `[0.0, 1.0]` when present
- at least one modality must be present
- training rows must include `true_label`

### Training CSV format

```csv
email_id,p_header,p_body,p_malware,true_label
e1,0.81,0.67,0.92,1
e2,0.10,0.22,,0
e3,0.54,0.61,0.18,1
```

### Inference CSV format

```csv
email_id,p_header,p_body,p_malware
e1001,0.82,0.71,0.93
e1002,0.11,0.18,
e1003,0.44,0.58,0.20
```

---

## 5. Output Contract

The fusion layer produces the following output:

```csv
email_id,final_score,final_label,risk_level,models_used,fusion_method
```

Example:

```csv
email_id,final_score,final_label,risk_level,models_used,fusion_method
e1001,0.88,1,high / malicious,header|body|malware,logistic_regression_stacking
e1002,0.16,0,low / benign,header|body,soft_voting
```

### Output field meanings

- `final_score`: final fused probability
- `final_label`: binary label using the configured threshold
- `risk_level`: mapped severity band
- `models_used`: which branch outputs were actually present
- `fusion_method`: which fusion approach produced the result

---

## 6. Logistic Regression Stacking Model

The logistic regression stacking model uses both the branch probabilities and explicit availability indicators.

### Raw probability inputs

- `p_header`
- `p_body`
- `p_malware`

### Derived model features

The stacking model is trained on the following internal feature set:

- `p_header_filled`
- `p_body_filled`
- `p_malware_filled`
- `has_header`
- `has_body`
- `has_malware`
- `models_present_count`

### Why these features are used

The filled probability fields allow the model to operate even when one modality is missing. The `has_*` indicators preserve the fact that a modality was actually absent, which gives the meta-model enough context to avoid treating an imputed value as if it were a true branch output.

### Current saved metadata

The current trained artifact stores metadata that includes:

- model type
- imputation value
- threat threshold
- feature columns
- logistic regression coefficients
- intercept
- number of training rows used

This metadata is saved in:

`artifacts/logistic_fusion_metadata.json`

---

## 7. Soft Voting Baseline

The soft-voting baseline computes the arithmetic mean of only the probabilities that are present.

Example:

- `p_header = 0.10`
- `p_body = 0.22`
- `p_malware = missing`

Soft-voting score:

```text
(0.10 + 0.22) / 2 = 0.16
```

This baseline is intentionally simple. It serves two purposes:

1. provide an interpretable comparison method
2. provide a fallback reference when explaining the value of the learned stacking model

---

## 8. Missing-Modality Handling

The system is designed so missing branches do not break inference.

### Expected missing case

Missing malware output is expected when there is no attachment.

### Soft-voting behavior

- ignores missing probabilities
- averages only available modalities
- does not invent a fake value for the average

### Logistic-stacking behavior

- fills missing probabilities with a neutral configured value (`0.50` by default)
- includes `has_malware = 0` or equivalent indicators
- includes `models_present_count`
- still returns one final score

### Explainability support

Every output includes a `models_used` field, which makes it easy to show whether the result was based on header only, body only, header plus body, or all three branches.

---

## 9. Risk Mapping

The final score is mapped to a risk band using the required project thresholds:

- `0.00 <= score < 0.30` → `low / benign`
- `0.30 <= score < 0.70` → `medium / suspicious`
- `0.70 <= score <= 1.00` → `high / malicious`

The binary `final_label` threshold is currently configured at `0.50`.

---

## 10. Current Local Validation Status

The fusion layer has been validated locally using both unit tests and end-to-end demo runs.

### Unit tests currently implemented

The current test suite covers:

- contract validation
- dataframe validation
- missing-modality handling
- preprocessing
- soft-voting behavior
- logistic fusion save/load behavior
- risk mapping boundaries

### Current test result

```text
21 passed
```

### Additional checks already run

In addition to the unit tests, the fusion layer has also been run through:

- logistic-regression stacking inference on sample data
- soft-voting inference on sample data
- side-by-side score comparison between the two methods
- edge-case modality tests including header-only, body-only, malware-only, and header-plus-body-without-malware examples
- Lambda + S3 utility tests for URI parsing, CSV round-trip, and handler S3-event flow

---

## 11. Current Example Results

### Logistic regression stacking sample outputs

```text
i1 -> 0.732685
i2 -> 0.372184
i3 -> 0.558709
i4 -> 0.516483
```

### Soft-voting sample outputs

```text
i1 -> 0.853333
i2 -> 0.170000
i3 -> 0.396667
i4 -> 0.530000
```

These comparisons show that the learned stacking model is behaving differently from the baseline and is not simply reproducing the average. That is useful when discussing why a trained fusion model is preferable to a simple probability mean.

---

## 12. Files That Matter Most

### Source code

- `src/contracts.py` — row-level contracts
- `src/validators.py` — dataframe validation
- `src/loaders.py` — CSV loading and writing
- `src/preprocess.py` — missing-modality and feature preparation
- `src/soft_voting.py` — baseline fusion logic
- `src/logistic_fusion.py` — logistic stacking model
- `src/risk_mapping.py` — score-to-risk logic
- `src/training.py` — training workflow
- `src/inference.py` — inference workflow

### Supporting files

- `config/fusion_config.yaml` — thresholds and settings
- `data/sample_fusion_train.csv` — sample training input
- `data/sample_fusion_inference.csv` — sample inference input
- `artifacts/logistic_fusion_model.joblib` — trained model artifact
- `artifacts/logistic_fusion_metadata.json` — explainability metadata
- `TEAM_DEMO.md` — demo walkthrough
- `run_demo.sh` — one-command verification script

---

## 13. How to Run the Model

### Run tests

```bash
pytest -q
```

### Train the fusion model

```bash
python3 train_fusion.py --input data/sample_fusion_train.csv
```

### Run logistic-regression stacking inference

```bash
python3 run_inference.py \
  --input data/sample_fusion_inference.csv \
  --fusion-method logistic_regression_stacking
```

### Run soft-voting inference

```bash
python3 run_inference.py \
  --input data/sample_fusion_inference.csv \
  --fusion-method soft_voting \
  --output artifacts/soft_voting_predictions.csv
```

### Run the full demo

```bash
./run_demo.sh
```

---

## 14. Cloud Runtime (Lambda + S3)

The fusion layer now supports a cloud runtime path through:

- `src/lambda_handler.py`
- `src/s3_io.py`

This allows the fusion system to run directly as a Lambda function that reads model probabilities from S3 and writes final fused outputs back to S3.


# S3 Does not save model probabilities
#     S3 instead saves individual processed emails
#      'processed': emails which feature extraction has been performed on
#     S3 also saves attachments & URL lists

### Lambda input options

#### Option A: direct invocation payload

```json
{
  "input_s3_uri": "s3://your-bucket/fusion-input/inference.csv",
  "output_s3_uri": "s3://your-bucket/fusion-output/predictions.csv",
  "fusion_method": "logistic_regression_stacking",
  "model_artifact_uri": "s3://your-bucket/artifacts/logistic_fusion_model.joblib",
  "config_s3_uri": "s3://your-bucket/config/fusion_config.yaml"
}
```

#### Option B: S3 event trigger

The handler can also accept native S3 object-created event payloads and extract bucket/key automatically.

### Lambda output payload

The handler returns metadata similar to:

```json
{
  "statusCode": 200,
  "message": "Fusion inference completed.",
  "fusion_method": "soft_voting",
  "input_s3_uri": "s3://...",
  "output_s3_uri": "s3://...",
  "rows_scored": 100,
  "output_columns": [
    "email_id",
    "final_score",
    "final_label",
    "risk_level",
    "models_used",
    "fusion_method"
  ]
}
```

### Runtime behavior

1. Resolve config and method
2. Resolve input source URI
3. Load CSV from S3
4. Validate contract and probabilities
5. Run fusion method
6. Write output CSV to S3
7. Return execution metadata

### Required IAM scope

At minimum, the Lambda execution role should include:

- `s3:GetObject` on fusion input prefix
- `s3:GetObject` on artifact/config prefix
- `s3:PutObject` on fusion output prefix

---

## 15. Current Readiness

At the current stage, the fusion model is ready as a standalone local component. The implemented work supports:

- local training
- local inference
- baseline comparison
- saved artifacts
- explainable outputs
- missing-modality support
- repeatable tests and demo runs

What remains is integration with the real branch outputs once the header, body, and malware models are finalized.

---

## 16. Next Integration Step

When the branch models are ready, the next step is to replace the sample inputs with real upstream outputs that conform to the same contract. At that point, the fusion layer should not require major redesign. The main work will be:

1. confirming branch output formatting
2. wiring those outputs into the fusion input contract
3. validating the end-to-end system with real examples
4. deciding how live inference should be deployed operationally

The current recommendation remains:

- train the fusion model offline
- use the trained artifact for inference
- integrate the live path through a service or Lambda once the full system is ready

---

## 17. Summary

The fusion model is the final decision layer of the multi-model cyber-threat system. It combines the header, body, and malware branch outputs into one final score while remaining modular, explainable, and robust to missing data. The current implementation already supports both the required baseline and primary fusion methods, has been validated locally, and is ready to be connected to the real branch outputs as soon as those components are finalized.
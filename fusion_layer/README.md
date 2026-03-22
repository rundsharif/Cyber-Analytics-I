# Fusion Layer for Multi-Model Cyber-Threat Analysis

This project implements a **standalone late-fusion layer** for a multi-model cyber-threat analysis pipeline. It starts **after upstream model prediction is already available** and combines the probability outputs from three specialized models:

1. **Header model**
2. **Body model**
3. **Malware / attachment model**

The fusion layer is designed for **Phase 1** requirements where the team must use **late fusion**, not end-to-end neural fusion. The primary fusion method is **logistic regression stacking**, and the baseline method is **soft voting**.

---

## Why this fusion layer exists

Upstream ingestion, AWS/S3 processing, and base-model training are intentionally out of scope here. This module assumes those parts of the platform already produce model-level probabilities per email.

The fusion layer is responsible for:

- validating those model outputs,
- handling missing modalities,
- combining them into a final threat score,
- mapping the score to a human-readable risk level,
- and returning an operationally simple final decision artifact.

This makes the fusion layer easy to maintain, easy to explain, and easy to integrate into the larger cyber analytics capstone platform.

---

## Phase 1 fusion approach

### Primary method: logistic regression stacking

The logistic fusion model takes the model probabilities as late-fusion inputs:

- `p_header`
- `p_body`
- `p_malware`

To support missing modalities, the stacking model also uses explicit **missingness indicators**:

- `has_header`
- `has_body`
- `has_malware`
- `models_present_count`

Missing probability values are filled with a configurable neutral value (`0.50` by default), while the missingness indicators tell the model which modalities were actually present.

### Baseline method: soft voting

Soft voting computes a simple average over the probabilities that are actually present.

Example:

- `p_header = 0.10`
- `p_body = 0.22`
- `p_malware = missing`

Soft voting score = `(0.10 + 0.22) / 2 = 0.16`

Missing malware is **not** forced into the average for the baseline.

---

## Input and output contracts

### Training input contract

CSV columns:

```csv
email_id,p_header,p_body,p_malware,true_label
```

Rules:

- `email_id` must be present and unique
- `p_header`, `p_body`, `p_malware` must be probabilities in `[0.0, 1.0]` or blank
- at least one model probability must be present for every row
- `true_label` must be `0` or `1`

Example:

```csv
email_id,p_header,p_body,p_malware,true_label
e1,0.81,0.67,0.92,1
e2,0.10,0.22,,0
e3,0.54,0.61,0.18,1
```

### Inference input contract

CSV columns:

```csv
email_id,p_header,p_body,p_malware
```

Rules:

- same validation rules as training input, except there is no `true_label`
- blank `p_malware` is expected when an email has no attachment or no malware-model output

### Fusion output contract

CSV columns:

```csv
email_id,final_score,final_label,risk_level,models_used,fusion_method
```

Field meanings:

- `final_score`: fused probability in `[0.0, 1.0]`
- `final_label`: binary decision using the configurable threshold (`0.50` by default)
- `risk_level`: mapped from the score bands below
- `models_used`: which source model scores were present, e.g. `header|body` or `header|body|malware`
- `fusion_method`: either `soft_voting` or `logistic_regression_stacking`

---

## Risk mapping

The project implements the professor's required risk bands:

- `0.00 <= score < 0.30` → `low / benign`
- `0.30 <= score < 0.70` → `medium / suspicious`
- `0.70 <= score <= 1.00` → `high / malicious`

The binary `final_label` threshold is configurable and defaults to:

- `score >= 0.50` → `1`
- `score < 0.50` → `0`

---

## Project structure

```text
fusion_layer/
├── README.md
├── requirements.txt
├── train_fusion.py
├── run_inference.py
├── config/
│   └── fusion_config.yaml
├── data/
│   ├── sample_fusion_train.csv
│   └── sample_fusion_inference.csv
├── src/
│   ├── __init__.py
│   ├── contracts.py
│   ├── loaders.py
│   ├── validators.py
│   ├── preprocess.py
│   ├── soft_voting.py
│   ├── logistic_fusion.py
│   ├── risk_mapping.py
│   ├── training.py
│   ├── inference.py
│   └── utils.py
├── tests/
│   ├── conftest.py
│   ├── test_contracts.py
│   ├── test_validators.py
│   ├── test_preprocess.py
│   ├── test_soft_voting.py
│   ├── test_logistic_fusion.py
│   └── test_risk_mapping.py
└── artifacts/
    └── .gitkeep
```

---

## Installation

From the `fusion_layer` directory:

```bash
python3 -m pip install -r requirements.txt
```

---

## Training the logistic fusion model

The training CLI reads labeled fusion rows, validates the schema, trains the logistic regression stacking model, and saves the model artifact with `joblib`.

### Using the included sample data

```bash
cd /Users/seth/Projects/Capstone1/Cyber-Analytics-I/fusion_layer
python3 train_fusion.py --input data/sample_fusion_train.csv
```

Default outputs:

- model artifact: `artifacts/logistic_fusion_model.joblib`
- metadata: `artifacts/logistic_fusion_metadata.json`

### Custom paths

```bash
python3 train_fusion.py   --input /path/to/fusion_train.csv   --model-output /path/to/logistic_fusion_model.joblib   --metadata-output /path/to/logistic_fusion_metadata.json
```

---

## Running inference

### Logistic regression stacking

```bash
cd /Users/seth/Projects/Capstone1/Cyber-Analytics-I/fusion_layer
python3 run_inference.py   --input data/sample_fusion_inference.csv   --fusion-method logistic_regression_stacking
```

If `--model-artifact` is omitted, the CLI uses the configured default artifact path.

### Soft voting baseline

```bash
python3 run_inference.py   --input data/sample_fusion_inference.csv   --fusion-method soft_voting   --output artifacts/soft_voting_predictions.csv
```

---

## How missing values are handled

Missing modalities are handled with explicit logic.

### Case: no attachment / no malware score

If an email has no attachment, `p_malware` can be blank.

#### Soft voting behavior

- averages only the available model scores
- does **not** inject a fake malware score into the mean

#### Logistic stacking behavior

- fills the missing probability with a configurable neutral value (`0.50` by default)
- adds a missingness feature (`has_malware = 0`)
- preserves explainability because the model can learn different behavior when malware is unavailable

### Why this design is useful

- simple to explain to instructors and teammates
- compatible with scikit-learn
- robust for operational use
- easy to extend later if new modalities are added

---

## Explainability notes

This project intentionally favors explainable, maintainable late fusion over complex neural fusion.

Explainability features include:

- explicit column contracts
- transparent missing-data handling
- interpretable logistic regression coefficients
- readable `models_used` field in inference outputs
- simple baseline comparator via soft voting

The training metadata JSON includes the fitted logistic regression coefficients and intercept for inspection.

---

## Testing

Run unit tests from the `fusion_layer` directory:

```bash
pytest -q
```

The tests cover:

- contract validation
- missing-modality handling
- preprocessing behavior
- soft voting outputs
- logistic fusion train/save/load/infer flow
- risk-level boundary behavior

---

## Quick team demo

If you want a one-command way to demonstrate the project to teammates:

```bash
./run_demo.sh
```

This will:

- run the unit tests
- train the logistic fusion model on the sample training CSV
- run logistic-regression stacking inference
- run soft-voting inference

See `TEAM_DEMO.md` for a walkthrough, current sample outputs, and suggested talking points.

---

## How this fits into the larger cyber-threat platform

This module belongs **after** the upstream prediction stage.

High-level flow:

1. upstream pipeline ingests and preprocesses emails
2. header, body, and malware specialists each produce probability outputs
3. this fusion layer reads those probabilities
4. fusion produces a final threat score and decision label
5. downstream systems can store, alert on, or visualize the final results

That separation keeps responsibilities clear:

- upstream teams own feature extraction and model generation
- this module owns late fusion, validation, and final decision logic

---

## Notes

- No AWS code is included here.
- No upstream base-model training is implemented here.
- No embedding fusion, transformer fusion, or end-to-end neural fusion is used.
- The design is intentionally modular, readable, and student-team friendly.

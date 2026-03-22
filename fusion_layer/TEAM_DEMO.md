## Fusion Layer Team Demo Guide

This file gives you a simple way to demonstrate that the fusion layer is fully wired up and working.

### Project location

```bash
cd /Users/seth/Projects/Capstone1/Cyber-Analytics-I/fusion_layer
```

---

## 1. Run the unit tests

This proves the main logic is working.

```bash
pytest -q
```

Expected result:

```text
12 passed
```

What this covers:
- contracts
- validators
- missing-modality handling
- preprocessing
- soft voting
- logistic regression fusion
- save/load artifact behavior
- risk mapping boundaries

---

## 2. Train the fusion model

This uses the included sample training CSV.

```bash
python3 train_fusion.py --input data/sample_fusion_train.csv
```

Expected outputs:
- `artifacts/logistic_fusion_model.joblib`
- `artifacts/logistic_fusion_metadata.json`

What to show your team:
- the logistic fusion model trains successfully
- the model artifact is persisted
- metadata includes feature names and coefficients for explainability

---

## 3. Run logistic-regression stacking inference

```bash
python3 run_inference.py \
  --input data/sample_fusion_inference.csv \
  --fusion-method logistic_regression_stacking
```

Output file:
- `artifacts/logistic_regression_stacking_predictions.csv`

The CLI now also prints the scoring table directly in the terminal, so you can show the results live without opening the CSV first.

Current sample output:

```csv
email_id,final_score,final_label,risk_level,models_used,fusion_method
i1,0.7326851896509923,1,high / malicious,header|body|malware,logistic_regression_stacking
i2,0.3721840110968995,0,medium / suspicious,header|body,logistic_regression_stacking
i3,0.5587085164979801,1,medium / suspicious,header|body|malware,logistic_regression_stacking
i4,0.5164826799861856,1,medium / suspicious,header|body,logistic_regression_stacking
```

What to show your team:
- missing malware is handled correctly for `i2` and `i4`
- `models_used` clearly shows when malware is absent
- the fusion output includes the final score, binary label, and risk level

---

## 4. Run soft-voting baseline inference

```bash
python3 run_inference.py \
  --input data/sample_fusion_inference.csv \
  --fusion-method soft_voting \
  --output artifacts/soft_voting_predictions.csv
```

Output file:
- `artifacts/soft_voting_predictions.csv`

The CLI also prints the soft-voting results directly in the terminal.

Current sample output:

```csv
email_id,final_score,final_label,risk_level,models_used,fusion_method
i1,0.8533333333333334,1,high / malicious,header|body|malware,soft_voting
i2,0.17,0,low / benign,header|body,soft_voting
i3,0.39666666666666667,0,medium / suspicious,header|body|malware,soft_voting
i4,0.53,1,medium / suspicious,header|body,soft_voting
```

What to show your team:
- this is the required baseline
- it averages only the modalities that are present
- it gives a simple comparison point against logistic stacking

---

## 5. Show the sample data that drives the demo

Sample inference input:

```csv
email_id,p_header,p_body,p_malware
i1,0.88,0.77,0.91
i2,0.14,0.20,
i3,0.49,0.58,0.12
i4,0.62,0.44,
```

The blank malware values are intentional and demonstrate missing-modality support.

---

## 6. One-command demo

If you want to rerun everything quickly:

```bash
./run_demo.sh
```

This will:
- run the tests
- retrain the logistic fusion model
- generate logistic stacking predictions
- generate soft-voting predictions

---

## 7. Suggested talking points for the team

- The fusion layer is complete and working as a standalone late-fusion component.
- It accepts upstream model probabilities from the header, body, and malware models.
- It supports missing malware inputs for emails without attachments.
- It implements both required methods: soft voting and logistic regression stacking.
- It produces explainable outputs with `models_used`, `fusion_method`, and risk levels.
- The current code is verified with unit tests and sample end-to-end runs.

---

## 8. What is still left for team integration

The main remaining work is integration with the rest of the platform:
- connecting real upstream probability outputs
- deciding the real-time architecture
- optionally adding Lambda/API/S3 support for live inference
- evaluating on real labeled project data
#!/bin/zsh

set -euo pipefail

echo "[1/5] Running unit tests..."
pytest -q

echo "[2/5] Training logistic fusion model..."
python3 train_fusion.py --input data/sample_fusion_train.csv

echo "[3/5] Running logistic regression stacking inference..."
python3 run_inference.py \
  --input data/sample_fusion_inference.csv \
  --fusion-method logistic_regression_stacking

echo "[4/5] Running soft voting inference..."
python3 run_inference.py \
  --input data/sample_fusion_inference.csv \
  --fusion-method soft_voting \
  --output artifacts/soft_voting_predictions.csv

echo "[5/5] Running integration-oriented fusion assembly demo..."
python3 run_integrated_fusion.py \
  --header-input data/sample_header_scores.csv \
  --body-input data/sample_body_scores.csv \
  --malware-input data/sample_malware_scores.csv \
  --fusion-method soft_voting \
  --assembled-input-output artifacts/assembled_fusion_input.csv \
  --manifest-output artifacts/integrated_soft_voting_manifest.json \
  --output artifacts/integrated_soft_voting_predictions.csv

echo ""
echo "Demo complete. Generated files:"
echo "- artifacts/logistic_fusion_model.joblib"
echo "- artifacts/logistic_fusion_metadata.json"
echo "- artifacts/logistic_regression_stacking_predictions.csv"
echo "- artifacts/soft_voting_predictions.csv"
echo "- artifacts/assembled_fusion_input.csv"
echo "- artifacts/integrated_soft_voting_manifest.json"
echo "- artifacts/integrated_soft_voting_predictions.csv"
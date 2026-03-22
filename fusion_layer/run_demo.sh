#!/bin/zsh

set -euo pipefail

echo "[1/4] Running unit tests..."
pytest -q

echo "[2/4] Training logistic fusion model..."
python3 train_fusion.py --input data/sample_fusion_train.csv

echo "[3/4] Running logistic regression stacking inference..."
python3 run_inference.py \
  --input data/sample_fusion_inference.csv \
  --fusion-method logistic_regression_stacking

echo "[4/4] Running soft voting inference..."
python3 run_inference.py \
  --input data/sample_fusion_inference.csv \
  --fusion-method soft_voting \
  --output artifacts/soft_voting_predictions.csv

echo ""
echo "Demo complete. Generated files:"
echo "- artifacts/logistic_fusion_model.joblib"
echo "- artifacts/logistic_fusion_metadata.json"
echo "- artifacts/logistic_regression_stacking_predictions.csv"
echo "- artifacts/soft_voting_predictions.csv"
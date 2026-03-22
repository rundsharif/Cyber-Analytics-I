#!/usr/bin/env python3
"""
train_email_model.py

Trains a BEHAVIORAL / ANOMALY classifier on numeric features produced by
build_behavior_features.py.

Run order:

    python3 build_behavior_features.py
    python3 train_email_model.py
"""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

BASE_DIR = Path(__file__).resolve().parent
FEAT_DIR = BASE_DIR / "behavior_features"

TRAIN_CSV = FEAT_DIR / "behavior_train.csv"
TEST_CSV = FEAT_DIR / "behavior_test.csv"
MODEL_PATH = BASE_DIR / "email_behavior_model.joblib"


def load_features():
    print(f"[+] Loading TRAIN features from {TRAIN_CSV}")
    train_df = pd.read_csv(TRAIN_CSV)

    print(f"[+] Loading TEST features from {TEST_CSV}")
    test_df = pd.read_csv(TEST_CSV)

    feature_cols = [
        "send_time_zscore",
        "body_length_zscore",
        "link_count_zscore",
        "attachment_count_zscore",
        "sender_seen_before",
        "first_contact_flag",
        "sender_prior_phish_rate",
        "domain_prior_phish_rate",
    ]

    X_train = train_df[feature_cols].values
    y_train = train_df["label"].values

    X_test = test_df[feature_cols].values
    y_test = test_df["label"].values

    print(
        f"[+] Train shape: {X_train.shape}, "
        f"Test shape: {X_test.shape}"
    )
    return X_train, y_train, X_test, y_test


def main():
    print("[+] Training behavioral / anomaly email model")

    X_train, y_train, X_test, y_test = load_features()

    # Simple, robust pipeline: scale + logistic regression
    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                max_iter=1000,
                n_jobs=-1,
                class_weight="balanced",
            )),
        ]
    )

    print("[+] Fitting model ...")
    pipeline.fit(X_train, y_train)

    print("[+] Evaluating on TEST set ...")
    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]

    print("\n=== Classification Report ===")
    print(classification_report(y_test, y_pred, digits=4))

    try:
        auc = roc_auc_score(y_test, y_proba)
        print(f"ROC-AUC: {auc:.4f}")
    except ValueError:
        print("ROC-AUC could not be computed (only one class present?).")

    print(f"\n[+] Saving model to {MODEL_PATH} ...")
    joblib.dump(pipeline, MODEL_PATH)
    print("[+] Done.")


if __name__ == "__main__":
    main()
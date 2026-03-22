# header_origin_train.py
import hashlib
from pathlib import Path
from collections import Counter

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    precision_recall_curve,
    average_precision_score,
)
from sklearn.model_selection import GroupShuffleSplit

# -------- Config --------
DATA_DIR = Path("header_features")
MAL_FILE = "trec_malicious_parsed_header_features.json"
BEN_FILE = "trec_benign_parsed_header_features.json"

SAVE_MODEL_PATH = "header_origin_trec_model.pkl"
SAVE_COLS_PATH = "header_origin_trec_columns.pkl"
RANDOM_STATE = 42

# -------- Utils --------
def pct(y):
    c = Counter(y); n = len(y)
    return {int(k): f"{c[k]} ({c[k]/n:.3%})" for k in sorted(c.keys())}

def row_signature(df: pd.DataFrame) -> pd.Series:
    df_str = df.astype(str)
    joined = df_str.agg("|".join, axis=1)
    return joined.apply(lambda s: hashlib.md5(s.encode()).hexdigest())

def prepare_features(df: pd.DataFrame):
    y = df["label"].astype(int)
    X = df.drop(columns=["label"], errors="ignore")
    bool_cols = X.select_dtypes(include=["bool"]).columns
    if len(bool_cols) > 0:
        X[bool_cols] = X[bool_cols].astype("int8")
    X = X.fillna(0)
    return X, y

# -------- Load --------
def load_trec_frames():
    mal = pd.read_json(DATA_DIR / MAL_FILE, lines=True); mal["label"] = 0
    ben = pd.read_json(DATA_DIR / BEN_FILE, lines=True); ben["label"] = 1
    return pd.concat([mal, ben], ignore_index=True)

def main():
    print("Training Header Origin Model (TREC)…")

    df = load_trec_frames()
    X_all, y_all = prepare_features(df)

    # Deduplicate on features only
    sig_all = row_signature(X_all)
    keep = ~sig_all.duplicated()
    X = X_all.loc[keep].reset_index(drop=True)
    y = y_all.loc[keep].reset_index(drop=True)
    print(f"Rows after feature-dedup: {len(X)}")

    # Grouped, stratified split (no overlap)
    groups = row_signature(X)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    train_idx, test_idx = next(gss.split(X, y, groups=groups))
    X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]
    y_tr, y_te = y.iloc[train_idx], y.iloc[test_idx]

    # Train
    model = RandomForestClassifier(
        n_estimators=250, class_weight="balanced",
        n_jobs=-1, random_state=RANDOM_STATE
    )
    model.fit(X_tr, y_tr)

    # Evaluate
    y_pred = model.predict(X_te)
    y_proba = model.predict_proba(X_te)[:, 1]

    print("Class distribution (train):", pct(y_tr))
    print("Class distribution (test):",  pct(y_te))
    print("\nClassification Report:\n", classification_report(y_te, y_pred))
    print("Confusion Matrix:\n", confusion_matrix(y_te, y_pred))
    print("ROC-AUC:", round(roc_auc_score(y_te, y_proba), 6))
    pr, rc, _ = precision_recall_curve(y_te, y_proba)
    print("Average Precision (PR AUC):", round(average_precision_score(y_te, y_proba), 6))

    # Save artifacts
    joblib.dump(model, SAVE_MODEL_PATH)
    joblib.dump(list(X.columns), SAVE_COLS_PATH)
    print(f"\nSaved: {SAVE_MODEL_PATH}, {SAVE_COLS_PATH}")

if __name__ == "__main__":
    main()
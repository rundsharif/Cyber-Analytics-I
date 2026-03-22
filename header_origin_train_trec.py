# header_origin_train_verify.py  (final, verified version)
import hashlib, json
from pathlib import Path
from collections import Counter

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    precision_recall_curve,
    average_precision_score,
)
from sklearn.model_selection import (
    train_test_split,
    StratifiedKFold,
    cross_val_score,
    GroupShuffleSplit,
)

# ---------------------- Config ----------------------
DATA_DIR = Path("header_features")
MAL_FILE = "trec_malicious_parsed_header_features.json"
BEN_FILE = "trec_benign_parsed_header_features.json"

SAVE_MODEL_PATH = "header_origin_trec_model.pkl"
SAVE_COLS_PATH = "header_origin_trec_columns.pkl"
METRICS_DIR = Path("metrics")

RANDOM_STATE = 42

# ---------------------- Utils -----------------------
def pct(x):
    c = Counter(x); n = len(x)
    return {int(k): f"{c[k]} ({c[k]/n:.3%})" for k in sorted(c.keys())}

def row_signature(df: pd.DataFrame) -> pd.Series:
    """Deterministic hash per row across all columns (as strings)."""
    df_str = df.astype(str)
    joined = df_str.agg("|".join, axis=1)
    return joined.apply(lambda s: hashlib.md5(s.encode()).hexdigest())

def prepare_features(df: pd.DataFrame):
    """Cast booleans to small ints, fill NaNs."""
    y = df["label"]
    X = df.drop(columns=["label"], errors="ignore")
    bool_cols = X.select_dtypes(include=["bool"]).columns
    if len(bool_cols) > 0:
        X[bool_cols] = X[bool_cols].astype("int8")
    X = X.fillna(0)
    return X, y

def threshold_table(y_true, y_proba, cutoffs=(0.2,0.3,0.4,0.5,0.6,0.7,0.8)):
    rows = []
    for t in cutoffs:
        y_hat = (y_proba >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, y_hat).ravel()
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2*precision*recall)/(precision+recall) if (precision+recall) else 0.0
        rows.append({"threshold": t, "precision": precision, "recall": recall, "f1": f1,
                     "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)})
    return pd.DataFrame(rows)

def print_and_save_metrics(split_name, y_test, y_pred, y_proba, class_dist_train, class_dist_test):
    METRICS_DIR.mkdir(exist_ok=True)
    print(f"\n=== {split_name} ===")
    print("Class distribution (train):", class_dist_train)
    print("Class distribution (test):",  class_dist_test)

    report = classification_report(y_test, y_pred, output_dict=True)
    cm = confusion_matrix(y_test, y_pred)
    roc = roc_auc_score(y_test, y_proba)
    p, r, t = precision_recall_curve(y_test, y_proba)
    ap = average_precision_score(y_test, y_proba)

    print("\nClassification Report:")
    print(pd.DataFrame(report).transpose().round(4))
    print("\nConfusion Matrix:\n", cm)
    print("ROC-AUC:", round(roc, 6))
    print("Average Precision (PR AUC):", round(ap, 6))

    thr = threshold_table(y_test, y_proba)
    print("\nThreshold table (precision/recall/F1):")
    print(thr.round(4).to_string(index=False))

    # Save artifacts
    pd.DataFrame(cm, index=["true_0","true_1"], columns=["pred_0","pred_1"]).to_csv(METRICS_DIR/f"confusion_{split_name}.csv")
    thr.to_csv(METRICS_DIR/f"thresholds_{split_name}.csv", index=False)
    with open(METRICS_DIR/f"metrics_{split_name}.json","w") as f:
        json.dump({
            "roc_auc": float(roc),
            "average_precision": float(ap),
            "class_distribution_train": class_dist_train,
            "class_distribution_test": class_dist_test,
            "classification_report": report,
        }, f, indent=2)

def train_and_report(model, X_train, y_train, X_test, y_test, split_name=""):
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    print_and_save_metrics(
        split_name,
        y_test, y_pred, y_proba,
        class_dist_train=pct(y_train),
        class_dist_test=pct(y_test),
    )
    return model, y_pred, y_proba

# ---------------------- Data load -------------------
def load_trec():
    mal_path = DATA_DIR / MAL_FILE
    ben_path = DATA_DIR / BEN_FILE
    if not mal_path.exists() or not ben_path.exists():
        raise FileNotFoundError(f"Missing {mal_path} or {ben_path} in {DATA_DIR}/")
    mal = pd.read_json(mal_path, lines=True); mal["label"] = 0
    ben = pd.read_json(ben_path, lines=True); ben["label"] = 1
    df = pd.concat([mal, ben], ignore_index=True)
    return df

# ------------------------- Main ---------------------
def main():
    print("Verifier version: 2025-11-08-fixed")
    df_raw = load_trec()
    print(f"Loaded {len(df_raw)} samples with {df_raw.shape[1]} columns from TREC.")

    # Prepare features FIRST, then deduplicate on features only
    X_all, y_all = prepare_features(df_raw)
    sig_all = row_signature(X_all)
    dup_count = sig_all.duplicated().sum()
    print(f"Exact duplicate FEATURE rows found (pre-split): {dup_count}")

    keep_mask = ~sig_all.duplicated()
    X = X_all.loc[keep_mask].reset_index(drop=True)
    y = y_all.loc[keep_mask].reset_index(drop=True)
    print(f"After dropping feature-duplicates: {len(X)} rows")

    # Persist columns for downstream inference
    cols = list(X.columns)
    joblib.dump(cols, SAVE_COLS_PATH)

    # ---------- 1) Stratified random split (with GroupShuffle to block any overlap) ----------
    # Use row signature as a "group" so train/test cannot share the same row
    groups = row_signature(X)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    train_idx, test_idx = next(gss.split(X, y, groups=groups))

    X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]
    y_tr, y_te = y.iloc[train_idx], y.iloc[test_idx]

    sig_tr = set(row_signature(X_tr)); sig_te = set(row_signature(X_te))
    overlap = len(sig_tr & sig_te)
    print(f"Train/Test overlap by row signature (stratified+grouped): {overlap}")

    rf = RandomForestClassifier(
        n_estimators=250, class_weight="balanced", n_jobs=-1, random_state=RANDOM_STATE
    )
    model, _, _ = train_and_report(rf, X_tr, y_tr, X_te, y_te, split_name="grouped_stratified_split")

    # Save stratified+grouped model for deployment
    joblib.dump(model, SAVE_MODEL_PATH)
    print(f"\nSaved model: {SAVE_MODEL_PATH}")
    print(f"Saved columns: {SAVE_COLS_PATH}")

    # ---------- 2) Deterministic hash-based split (no overlap by construction) ----------
    ID = row_signature(X)  # features-only
    def is_test(id_hash, pct=0.25):
        return (int(id_hash[-2:], 16) / 255.0) < pct
    mask_test = ID.apply(is_test)

    X_train_h, X_test_h = X[~mask_test], X[mask_test]
    y_train_h, y_test_h = y[~mask_test], y[mask_test]

    sig_tr_h = set(row_signature(X_train_h)); sig_te_h = set(row_signature(X_test_h))
    overlap_h = len(sig_tr_h & sig_te_h)
    print(f"\nTrain/Test overlap by row signature (hash split): {overlap_h}")

    rf_h = RandomForestClassifier(
        n_estimators=250, class_weight="balanced", n_jobs=-1, random_state=RANDOM_STATE
    )
    _model_h, _, _ = train_and_report(rf_h, X_train_h, y_train_h, X_test_h, y_test_h, split_name="hash_split")

    # Save tree-based feature importance for the hash split
    METRICS_DIR.mkdir(exist_ok=True)
    fi = pd.Series(_model_h.feature_importances_, index=X.columns).sort_values(ascending=False)
    fi.to_csv(METRICS_DIR/"feature_importance_hash_split_tree.csv")

    # ---------- 3) 5-fold Stratified CV ----------
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    rf_cv = RandomForestClassifier(
        n_estimators=250, class_weight="balanced", n_jobs=-1, random_state=RANDOM_STATE
    )
    auc = cross_val_score(rf_cv, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
    print(f"\n5-fold Stratified CV ROC-AUC: mean={auc.mean():.6f} ± {auc.std():.6f}")
    with open(METRICS_DIR/"metrics_cv.json","w") as f:
        json.dump({"cv_roc_auc_mean": float(auc.mean()), "cv_roc_auc_std": float(auc.std())}, f, indent=2)

    # ---------- 4) Shuffle-label sanity test (5-fold CV) ----------
    y_shuf = y.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True)
    X_shuf = X.reset_index(drop=True)

    rf_shuf = RandomForestClassifier(
        n_estimators=250, class_weight="balanced", n_jobs=-1, random_state=RANDOM_STATE
    )
    auc_shuf = cross_val_score(rf_shuf, X_shuf, y_shuf, cv=cv, scoring="roc_auc", n_jobs=-1)
    print(f"\nShuffle-label sanity CV AUC (expect ~0.5): mean={auc_shuf.mean():.3f} ± {auc_shuf.std():.3f}")
    with open(METRICS_DIR/"metrics_shuffle.json","w") as f:
        json.dump({"shuffle_cv_auc_mean": float(auc_shuf.mean()), "shuffle_cv_auc_std": float(auc_shuf.std())}, f, indent=2)

    # ---------- 5) Permutation importance (hash split holdout) ----------
    rf_perm = RandomForestClassifier(
        n_estimators=250, class_weight="balanced", n_jobs=-1, random_state=RANDOM_STATE
    )
    rf_perm.fit(X_train_h, y_train_h)
    perm = permutation_importance(
        rf_perm, X_test_h, y_test_h, n_repeats=5, random_state=RANDOM_STATE, n_jobs=-1
    )
    pi = pd.Series(perm.importances_mean, index=X.columns).sort_values(ascending=False)
    pi.to_csv(METRICS_DIR/"feature_importance_hash_split_permutation.csv")
    print("\nSaved permutation and tree-based importances to metrics/")

if __name__ == "__main__":
    main()
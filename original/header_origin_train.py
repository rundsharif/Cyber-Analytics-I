import zipfile
from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
import joblib

ZIP_PATH = Path("featured_headers.zip")
EXTRACT_DIR = Path("featured_headers")

def load_ndjson(p: Path) -> pd.DataFrame:
    return pd.read_json(p, lines=True)

def main():
    # 1) Extract once
    if not EXTRACT_DIR.exists():
        with zipfile.ZipFile(ZIP_PATH, "r") as z:
            z.extractall(EXTRACT_DIR)

    inner = EXTRACT_DIR / "featured_headers"
    evil = load_ndjson(inner / "evil_emls_features.json")
    privacy = load_ndjson(inner / "privacymail_features.json")
    dnc = load_ndjson(inner / "dnc_eml_features.json")

    # 2) Labels: 0 = malicious/spoofed, 1 = legitimate
    evil["label"] = 0
    privacy["label"] = 1
    dnc["label"] = 1

    df = pd.concat([evil, privacy, dnc], ignore_index=True)
    print(f"Loaded {len(df)} rows, {df.shape[1]} columns.")

    y = df["label"]
    X = df.drop(columns=["label"])

    # Cast booleans → small ints; fill missing
    bool_cols = X.select_dtypes(include=["bool"]).columns
    X[bool_cols] = X[bool_cols].astype("int8")
    X = X.fillna(0)

    # 3) Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    # 4) Model
    rf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        n_jobs=-1,
        random_state=42
    )
    rf.fit(X_train, y_train)

    # 5) Eval
    y_pred = rf.predict(X_test)
    print("\nClassification Report:\n", classification_report(y_test, y_pred))
    print("Confusion Matrix:\n", confusion_matrix(y_test, y_pred))

    # Optional: quick CV to sanity-check leakage
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    auc = cross_val_score(rf, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
    print(f"\n5-fold ROC-AUC: mean={auc.mean():.4f} ± {auc.std():.4f}")

    # 6) Save artifacts
    joblib.dump(rf, "header_origin_model.pkl")
    joblib.dump(list(X.columns), "header_origin_columns.pkl")
    print("\nSaved:")
    print(" - header_origin_model.pkl")
    print(" - header_origin_columns.pkl")

if __name__ == "__main__":
    main()
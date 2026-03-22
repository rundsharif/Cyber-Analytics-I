# evaluate_header_origin.py
import zipfile
from pathlib import Path
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score

# --- Load trained artifacts ---
model = joblib.load("header_origin_model.pkl")
cols = joblib.load("header_origin_columns.pkl")

# --- Reload dataset (same as training) ---
ZIP_PATH = Path("featured_headers.zip")
EXTRACT_DIR = Path("featured_headers")
if not EXTRACT_DIR.exists():
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(EXTRACT_DIR)
inner = EXTRACT_DIR / "featured_headers"

def load_ndjson(p: Path) -> pd.DataFrame:
    return pd.read_json(p, lines=True)

evil = load_ndjson(inner / "evil_emls_features.json"); evil["label"] = 0
privacy = load_ndjson(inner / "privacymail_features.json"); privacy["label"] = 1
dnc = load_ndjson(inner / "dnc_eml_features.json"); dnc["label"] = 1

df = pd.concat([evil, privacy, dnc], ignore_index=True)

# --- Prepare features/labels exactly like training ---
y = df["label"]
X = df.drop(columns=["label"]).reindex(columns=cols, fill_value=0)
bool_cols = X.select_dtypes(include=["bool"]).columns
if len(bool_cols) > 0:
    X[bool_cols] = X[bool_cols].astype("int8")

# --- Split and evaluate ---
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

y_pred = model.predict(Xte)
y_proba = model.predict_proba(Xte)[:, 1]

print("\nShapes:", X.shape, "train:", Xtr.shape, "test:", Xte.shape)
print("\nClassification Report:\n", classification_report(yte, y_pred))
print("Confusion Matrix:\n", confusion_matrix(yte, y_pred))
print("ROC-AUC:", roc_auc_score(yte, y_proba))
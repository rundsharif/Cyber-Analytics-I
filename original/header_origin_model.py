import zipfile
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
import joblib

# ----------------------------
# 1. Extract the zip file
# ----------------------------
zip_path = Path("featured_headers.zip")
extract_dir = Path("featured_headers")

if not extract_dir.exists():
    print("Extracting featured_headers.zip...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)
else:
    print("Already extracted.")

# The JSONs are likely inside a subfolder called 'featured_headers'
inner_dir = extract_dir / "featured_headers"

# ----------------------------
# 2. Load and label datasets
# ----------------------------
def load_json(path):
    """Read newline-delimited JSON (one record per line)."""
    return pd.read_json(path, lines=True)

evil = load_json(inner_dir / "evil_emls_features.json")
evil["label"] = 0  # malicious

privacy = load_json(inner_dir / "privacymail_features.json")
privacy["label"] = 1  # legitimate

dnc = load_json(inner_dir / "dnc_eml_features.json")
dnc["label"] = 1  # legitimate

df = pd.concat([evil, privacy, dnc], ignore_index=True)
print(f"Loaded {len(df)} total samples.")

# ----------------------------
# 3. Prepare features
# ----------------------------
y = df["label"]
X = df.drop(columns=["label"])

# Convert booleans to integers (0/1)
X = X.applymap(lambda v: int(v) if isinstance(v, bool) else v)
X = X.fillna(0)

# ----------------------------
# 4. Train / test split
# ----------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=42, stratify=y
)

# ----------------------------
# 5. Train Random Forest model
# ----------------------------
model = RandomForestClassifier(
    n_estimators=200,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

# ----------------------------
# 6. Evaluate model
# ----------------------------
y_pred = model.predict(X_test)
print("\nClassification Report:\n", classification_report(y_test, y_pred))
print("Confusion Matrix:\n", confusion_matrix(y_test, y_pred))

# Feature importances
feat_imp = pd.Series(model.feature_importances_, index=X.columns)
print("\nTop 15 Important Features:")
print(feat_imp.sort_values(ascending=False).head(15))

# ----------------------------
# 7. Save model and columns
# ----------------------------
joblib.dump(model, "header_origin_model.pkl")
joblib.dump(list(X.columns), "header_origin_columns.pkl")

print("\nModel and feature list saved:")
print(" - header_origin_model.pkl")
print(" - header_origin_columns.pkl")
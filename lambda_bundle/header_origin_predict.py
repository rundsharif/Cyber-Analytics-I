# header_origin_predict.py
import joblib
import pandas as pd
from pathlib import Path
from termcolor import colored  # pip install termcolor

MODEL_PATH = Path("header_origin_trec_model.pkl")
COLS_PATH = Path("header_origin_trec_columns.pkl")

# ------------------- Load -------------------
_model = joblib.load(MODEL_PATH)
_cols = joblib.load(COLS_PATH)

# ------------------- Core Predictor -------------------
def predict_header_trust(header_features: dict) -> float:
    """Predicts the probability that an email header is legitimate (0–1)."""
    row = pd.DataFrame([header_features]).reindex(columns=_cols, fill_value=0).fillna(0)
    for c in row.columns:
        if row[c].dropna().isin([0, 1, True, False]).all():
            row[c] = row[c].astype("int8")
    return float(_model.predict_proba(row)[0, 1])

# ------------------- Explainability -------------------
def explain_sample(header_features: dict, top_n: int = 10):
    """Shows which global feature importances likely influenced this sample."""
    fi = pd.Series(_model.feature_importances_, index=_cols)
    fi = fi[fi > 0].sort_values(ascending=False)
    row = pd.DataFrame([header_features]).reindex(columns=fi.index, fill_value=0).fillna(0)
    vals = row.loc[0, fi.index]
    df = pd.DataFrame({"Importance": fi, "Value": vals}).head(top_n)
    print("\nTop Important Features (global view):")
    print(df.round(4).to_string(index=True))

# ------------------- Visual Wrapper -------------------
def display_prediction(score: float):
    """Pretty print of the header_trust_score result."""
    print("\n───────────────────────────────────────────────")
    print(colored(" Header Trust Model Result", "cyan", attrs=["bold"]))
    print("───────────────────────────────────────────────")

    if score >= 0.8:
        label = colored("LEGITIMATE", "green", attrs=["bold"])
    elif score >= 0.5:
        label = colored("REVIEW / UNCERTAIN", "yellow", attrs=["bold"])
    else:
        label = colored("SUSPICIOUS", "red", attrs=["bold"])

    print(f" header_trust_score: {score:.4f}  →  {label}")
    print("───────────────────────────────────────────────")

# ------------------- Main -------------------
if __name__ == "__main__":
    sample = {
        "from_return_mismatch": 1,
        "received_count": 3,
        "unique_relay_ips": 2,
        "ip_diversity_ratio": 0.6,
        "has_spf": 1,
        "has_dkim": 1,
        "has_auth_results": 1,
        "has_x_mailer": 1,
        "timezone_offset": 0,
        "reply_to_differs": 0,
        "display_name_empty": 0,
        "content_type_complexity": 2,
        "sent_business_hours": 1,
        "day_of_week": 2,
        "from_free_provider": 0,
    }

    score = predict_header_trust(sample)
    display_prediction(score)
    explain_sample(sample)
    print()
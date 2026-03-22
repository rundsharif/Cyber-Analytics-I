import joblib
import pandas as pd

MODEL_PATH = "header_origin_model.pkl"
COLS_PATH = "header_origin_columns.pkl"

_rf = joblib.load(MODEL_PATH)
_cols = joblib.load(COLS_PATH)

# Infer boolean-ish columns by value set {0,1,True,False} on first call
_bool_cols = None

def predict_header_trust(header_features: dict) -> float:
    """
    Returns probability that header is legitimate (1.0 = high trust).
    Expects the same fields used in training (missing become 0).
    """
    global _bool_cols

    row = pd.DataFrame([header_features])
    row = row.reindex(columns=_cols, fill_value=0)

    if _bool_cols is None:
        guess = []
        for c in row.columns:
            vals = row[c].dropna().unique()
            if set(vals).issubset({0,1,True,False}):
                guess.append(c)
        _bool_cols = guess

    if _bool_cols:
        row[_bool_cols] = row[_bool_cols].astype("int8")

    row = row.fillna(0)
    prob_legit = _rf.predict_proba(row)[0][1]
    return float(prob_legit)
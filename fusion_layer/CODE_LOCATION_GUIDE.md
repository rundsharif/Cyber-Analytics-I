# Fusion Layer Code Location Guide

## Core Fusion Methods - Where the Scoring Happens

### 1. Soft Voting Fusion (Baseline Method)
**File:** `src/soft_voting.py`

**Key Code:**
```python
class SoftVotingFusion:
    """Average available probabilities across present modalities only."""
    
    def predict_scores(self, inference_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        annotated = annotate_model_availability(inference_df)
        # This is the actual scoring: simple average of available scores
        scores = annotated.loc[:, list(MODEL_PROBABILITY_COLUMNS)].mean(axis=1, skipna=True)
        return annotated, scores.astype(float)
```

**What it does:**
- Line 22: `mean(axis=1, skipna=True)` - Takes average of [p_header, p_body, p_malware], skipping missing values
- If all 3 present: (0.88 + 0.77 + 0.91) / 3
- If malware missing: (0.88 + 0.77) / 2

---

### 2. Logistic Regression Stacking (Primary Method)
**File:** `src/logistic_fusion.py`

**Key Code:**

#### Training (Line 61-70):
```python
def fit(self, training_df: pd.DataFrame) -> "LogisticFusionModel":
    """Fit the stacking model on labeled fusion rows."""
    
    _, feature_frame = prepare_logistic_features(
        training_df,
        imputation_value=self.imputation_value,
    )
    target = training_df["true_label"].astype(int)
    # This is where the weights are learned:
    self.estimator.fit(feature_frame[self.feature_columns_], target)
    return self
```

#### Inference (Line 72-82):
```python
def predict_scores(self, inference_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Return fused probabilities for an inference dataframe."""
    
    self._ensure_fitted()
    annotated, feature_frame = prepare_logistic_features(
        inference_df,
        imputation_value=self.imputation_value,
    )
    # This is the actual scoring: logistic regression prediction
    probabilities = self.estimator.predict_proba(feature_frame[self.feature_columns_])[:, 1]
    score_series = pd.Series(probabilities, index=inference_df.index, name="final_score")
    return annotated, score_series
```

**What it does:**
- Line 80: `predict_proba()` - Applies learned weights to features
- Under the hood, scikit-learn does: `sigmoid(w₀ + w₁×f₁ + w₂×f₂ + ... + w₇×f₇)`
- Returns probability between 0.0 and 1.0

---

### 3. Feature Engineering (Missing Data Handling)
**File:** `src/preprocess.py`

**Key Code (Lines 31-72):**
```python
def prepare_logistic_features(
    dataframe: pd.DataFrame,
    imputation_value: float = 0.50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prepare feature frame for logistic regression stacking."""
    
    annotated = dataframe.copy()
    
    # Step 1: Create indicator variables (binary 1/0)
    annotated["has_header"] = (~annotated["p_header"].isna()).astype(int)
    annotated["has_body"] = (~annotated["p_body"].isna()).astype(int)
    annotated["has_malware"] = (~annotated["p_malware"].isna()).astype(int)
    annotated["models_present_count"] = (
        annotated["has_header"] + annotated["has_body"] + annotated["has_malware"]
    )
    
    # Step 2: Fill missing probability values with neutral imputation
    annotated["p_header_filled"] = annotated["p_header"].fillna(imputation_value)
    annotated["p_body_filled"] = annotated["p_body"].fillna(imputation_value)
    annotated["p_malware_filled"] = annotated["p_malware"].fillna(imputation_value)
    
    # Step 3: Create feature dataframe with exactly these 7 features
    feature_frame = annotated.loc[:, list(LOGISTIC_FEATURE_COLUMNS)].copy()
    
    return annotated, feature_frame
```

**What it does:**
1. **Lines 41-45:** Create indicator features (has_header, has_body, has_malware, models_present_count)
2. **Lines 48-50:** Fill missing values with 0.5 (neutral probability)
3. **Line 53:** Return 7-feature vector: `[p_header_filled, p_body_filled, p_malware_filled, has_header, has_body, has_malware, models_present_count]`

---

## Complete Workflow Example

### Step-by-Step Code Flow for One Email:

**Input:**
```python
email = {
    "email_id": "5b297a3f-...",
    "p_header": 0.88,
    "p_body": 0.77,
    "p_malware": np.nan  # Missing - no attachment
}
```

**Step 1: Feature Engineering** (`src/preprocess.py`)
```python
features = prepare_logistic_features(email)
# Result:
# p_header_filled = 0.88
# p_body_filled = 0.77
# p_malware_filled = 0.50  (imputed)
# has_header = 1
# has_body = 1
# has_malware = 0  (missing!)
# models_present_count = 2
```

**Step 2: Apply Logistic Regression** (`src/logistic_fusion.py`)
```python
model = LogisticFusionModel.load("artifacts/logistic_fusion_model.joblib")
scores = model.predict_scores(email)
# Under the hood (scikit-learn):
# logit = -0.261 + (0.881×0.88) + (0.692×0.77) + (0.377×0.50) + (-0.261×1) + (-0.261×1) + (0.426×0) + (-0.095×2)
# logit = 0.372
# score = 1/(1 + e^(-0.372)) = 0.592
```

**Step 3: Apply Thresholds** (`src/risk_mapping.py`)
```python
final_label = 1 if score >= 0.5 else 0  # 0.592 >= 0.5 → label = 1
risk_level = map_risk_level(score)  # 0.592 → "medium"
```

---

## How to View the Actual Weights

**Trained Model Weights File:** `artifacts/logistic_fusion_metadata.json`

```json
{
  "coefficients": {
    "p_header_filled": 0.880530174651241,
    "p_body_filled": 0.6923285879253187,
    "p_malware_filled": 0.37647799568485724,
    "has_header": -0.260681977916206,
    "has_body": -0.260681977916206,
    "has_malware": 0.42596808938114994,
    "models_present_count": -0.09539586645126184
  },
  "intercept": -0.260681977916206
}
```

**To print weights in Python:**
```python
from src.logistic_fusion import LogisticFusionModel

model = LogisticFusionModel.load("artifacts/logistic_fusion_model.joblib")
weights = model.coefficients()
print(weights)
```

---

## Testing the Code

**Run soft voting:**
```bash
cd /Users/seth/Projects/Capstone1/Cyber-Analytics-I/fusion_layer
python3 -c "
from src.soft_voting import SoftVotingFusion
import pandas as pd

df = pd.DataFrame({
    'email_id': ['test1'],
    'p_header': [0.88],
    'p_body': [0.77],
    'p_malware': [0.91]
})

fusion = SoftVotingFusion(threat_threshold=0.5)
result = fusion.predict(df)
print(result)
"
```

**Run logistic regression:**
```bash
python3 -c "
from src.logistic_fusion import LogisticFusionModel
import pandas as pd

df = pd.DataFrame({
    'email_id': ['test1'],
    'p_header': [0.88],
    'p_body': [0.77],
    'p_malware': [0.91]
})

model = LogisticFusionModel.load('artifacts/logistic_fusion_model.joblib')
result = model.predict(df)
print(result)
"
```

---

## Summary of Key Files

| File | Purpose | Key Lines |
|------|---------|-----------|
| `src/soft_voting.py` | Baseline fusion method | Line 22: `scores = ...mean(axis=1, skipna=True)` |
| `src/logistic_fusion.py` | Primary fusion method | Line 80: `probabilities = self.estimator.predict_proba(...)` |
| `src/preprocess.py` | Feature engineering | Lines 41-50: Create indicators & impute missing values |
| `src/risk_mapping.py` | Score → risk level | Line 14-20: Threshold logic |
| `artifacts/logistic_fusion_model.joblib` | Trained model weights | Binary file (use joblib.load()) |
| `artifacts/logistic_fusion_metadata.json` | Human-readable weights | JSON coefficients |

---

## To Dive Deeper in Your Presentation

**Show this code snippet:**
```python
# src/logistic_fusion.py - Line 80
probabilities = self.estimator.predict_proba(feature_frame[self.feature_columns_])[:, 1]
```

**Explain:**
"This single line applies our trained logistic regression model. The model has learned these weights from labeled data:"
- Header: 0.881 (highest - most predictive)
- Body: 0.692 (strong)  
- Malware: 0.377 (moderate)

"It multiplies each feature by its weight, sums them, applies sigmoid function, and returns the final threat probability."

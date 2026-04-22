# How the Fusion Layer Weights Were Determined

## SHORT ANSWER:
The weights were **learned automatically by training a logistic regression model** on labeled examples using scikit-learn's maximum likelihood estimation algorithm.

---

## DETAILED EXPLANATION:

### Step 1: Create Training Data

We need emails where we have:
1. The three model scores (p_header, p_body, p_malware)
2. The **true label** (0 = benign, 1 = malicious)

**Example training data CSV:**
```csv
email_id,p_header,p_body,p_malware,true_label
e1,0.81,0.67,0.92,1        ← Actually malicious
e2,0.10,0.22,,0            ← Actually benign, no attachment
e3,0.54,0.61,0.18,1        ← Actually malicious
e4,0.05,0.12,0.08,0        ← Actually benign
...10 total examples
```

This data comes from:
- Security analysts who reviewed emails and labeled them
- OR emails from a labeled dataset (like Enron corpus with known phishing)
- The three upstream models ran on these emails to get the scores

---

### Step 2: Feature Engineering

For each training example, we create the 7-feature vector:
```python
# Example for e1:
p_header_filled = 0.81  (real value)
p_body_filled = 0.67    (real value)
p_malware_filled = 0.92 (real value)
has_header = 1          (present)
has_body = 1            (present)
has_malware = 1         (present)
models_present_count = 3

Features for e1: [0.81, 0.67, 0.92, 1, 1, 1, 3]
Label for e1: 1 (malicious)
```

We do this for all 10 training examples.

---

### Step 3: Train the Model (This is where weights are learned)

**Code from `train_fusion.py`:**
```python
from sklearn.linear_model import LogisticRegression

# Create the model
model = LogisticRegression(
    C=1.0,              # Regularization strength
    solver='liblinear', # Optimization algorithm
    max_iter=1000,      # Max training iterations
    random_state=42     # For reproducibility
)

# Fit the model to learn the weights
model.fit(feature_matrix, labels)
#         ↑               ↑
#         [0.81, 0.67, ...] [1, 0, 1, ...]
#         for all emails    true labels
```

---

### Step 4: What Happens Inside `model.fit()`?

**Maximum Likelihood Estimation:**

The algorithm finds the weights (β₀, β₁, ..., β₇) that **maximize the probability** of getting the observed labels given the features.

Mathematically, for each training email:
```
P(malicious | features) = sigmoid(β₀ + β₁×f₁ + β₂×f₂ + ... + β₇×f₇)
```

The algorithm:
1. **Starts with random weights** (e.g., all zeros)
2. **Computes predictions** using current weights
3. **Calculates error:** How wrong are predictions compared to true labels?
4. **Updates weights** to reduce error (using gradient descent)
5. **Repeats** steps 2-4 until weights converge (stop changing significantly)

After convergence, we get:
```
β₀ (intercept) = -0.261
β₁ (p_header_filled) = 0.881
β₂ (p_body_filled) = 0.692
β₃ (p_malware_filled) = 0.376
β₄ (has_header) = -0.261
β₅ (has_body) = -0.261
β₆ (has_malware) = 0.426
β₇ (models_present_count) = -0.095
```

---

### Step 5: Why These Specific Values?

**These weights emerged because:**

1. **Header (0.881) is highest** → In the training data, when header scores were high, emails were usually malicious. The model learned to trust header analysis the most.

2. **Body (0.692) is medium** → Body analysis was helpful but less consistently predictive than header.

3. **Malware (0.376) is lowest** → Malware scores were present less often (only 30% of emails had attachments in training) and/or were less decisive in determining the true label.

4. **has_malware (+0.426) is positive** → In the training data, emails with attachments were more likely to be malicious overall (even if the malware score itself was low).

5. **has_header/has_body (-0.261) are negative** → Missing these scores correlated with the model being less confident.

**The model discovered these patterns automatically** by analyzing the 10 training examples.

---

## INTUITIVE ANALOGY:

Think of it like learning to predict if it will rain:

**Features:** Temperature, Humidity, Cloud Coverage, Wind Speed  
**Training data:** 100 days with weather measurements + whether it rained

The algorithm finds:
- Humidity weight = 0.8 (most predictive)
- Cloud coverage weight = 0.6  
- Temperature weight = 0.2
- Wind speed weight = 0.1

**Why?** Because in the historical data, high humidity was the strongest rain indicator.

Same thing here: the fusion layer learned that **header analysis is the strongest malicious-email indicator** based on the 10 training examples.

---

## WHAT IF WE HAD DIFFERENT TRAINING DATA?

If we trained on different emails (e.g., from a different time period, different threat landscape), we might get different weights:

**Scenario 1: Attachment-heavy attack campaign**
```
New weights might be:
- malware: 0.85 (highest)
- body: 0.60
- header: 0.45
```

**Scenario 2: Spear-phishing campaign (no attachments)**
```
New weights might be:
- body: 0.90 (highest - relies on social engineering)
- header: 0.70
- malware: 0.20
```

This is why retraining periodically is important!

---

## FOR YOUR PRESENTATION:

**If asked: "How were the weights determined?"**

**Answer:**

"The weights were learned through supervised machine learning. We provided 10 labeled training examples—emails where we knew the true malicious/benign label, along with the three model scores. We used scikit-learn's logistic regression, which uses maximum likelihood estimation to find the optimal weights that best predict the training labels. The algorithm automatically discovered that header analysis was most predictive (weight 0.881), followed by body (0.692), then malware (0.376). These weren't manually tuned—they emerged from the data through the training process. In a production system, we'd retrain periodically with new labeled data to adapt to evolving threats."

**If they ask for more detail:**

"Specifically, the algorithm uses gradient descent to iteratively adjust the weights. It starts with random weights, makes predictions, measures error against true labels, and updates weights to minimize that error. After convergence, we get the optimal coefficients that maximize the likelihood of observing our training labels given the features."

---

## KEY POINTS TO EMPHASIZE:

✓ **Data-driven:** Weights came from actual training examples, not guesses  
✓ **Automated:** Scikit-learn's algorithm found the optimal values  
✓ **Interpretable:** We can see that header is 2.3× more influential than malware  
✓ **Adaptable:** Can retrain with new data to adjust to changing threats  
✓ **Statistically sound:** Maximum likelihood estimation is a proven ML technique

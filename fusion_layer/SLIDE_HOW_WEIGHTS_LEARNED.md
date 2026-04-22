# Slide: How Weights Were Determined
## HOW WERE THE WEIGHTS LEARNED?
### Training the Fusion Model

---

## SLIDE LAYOUT OPTION 1: Step-by-Step Process

```
┌─────────────────────────────────────────────────────────────────┐
│ HOW WERE THE WEIGHTS LEARNED?                                   │
│ Training the Fusion Model Through Supervised Machine Learning   │
└─────────────────────────────────────────────────────────────────┘

STEP 1: GATHER TRAINING DATA
┌────────────────────────────────────────────────────────┐
│ 10 labeled emails with:                                │
│ • Three model scores (p_header, p_body, p_malware)    │
│ • True label (0=benign, 1=malicious)                  │
│                                                         │
│ Example:                                               │
│ e1: [header=0.81, body=0.67, malware=0.92] → Label: 1 │
│ e2: [header=0.10, body=0.22, malware=NA] → Label: 0   │
└────────────────────────────────────────────────────────┘
                        ↓
STEP 2: FEATURE ENGINEERING
┌────────────────────────────────────────────────────────┐
│ Transform into 7-feature vectors:                      │
│ [p_header, p_body, p_malware, has_header,             │
│  has_body, has_malware, count]                        │
│                                                         │
│ e1: [0.81, 0.67, 0.92, 1, 1, 1, 3] → Label: 1        │
│ e2: [0.10, 0.22, 0.50, 1, 1, 0, 2] → Label: 0        │
└────────────────────────────────────────────────────────┘
                        ↓
STEP 3: TRAIN LOGISTIC REGRESSION
┌────────────────────────────────────────────────────────┐
│ Scikit-learn finds optimal weights using               │
│ Maximum Likelihood Estimation:                         │
│                                                         │
│ • Starts with random weights                           │
│ • Iteratively adjusts to minimize prediction error     │
│ • Converges to optimal values                          │
└────────────────────────────────────────────────────────┘
                        ↓
RESULT: LEARNED WEIGHTS
┌────────────────────────────────────────────────────────┐
│ Header:  0.881  ← Highest (most predictive)           │
│ Body:    0.692  ← Medium                               │
│ Malware: 0.376  ← Lowest                               │
│                                                         │
│ These emerged from DATA, not manual tuning            │
└────────────────────────────────────────────────────────┘
```

---

## SLIDE LAYOUT OPTION 2: Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│        HOW LOGISTIC REGRESSION LEARNS WEIGHTS               │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐
│  TRAINING DATA   │     10 labeled emails
│  (Input)         │     [scores + true labels]
└────────┬─────────┘
         │
         ↓
┌──────────────────────────────────────────────────────────┐
│           LOGISTIC REGRESSION ALGORITHM                   │
│           (Scikit-Learn)                                  │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ 1. Initialize random weights                        │ │
│  │ 2. Compute predictions with current weights         │ │
│  │ 3. Calculate error vs. true labels                  │ │
│  │ 4. Adjust weights to reduce error (gradient descent)│ │
│  │ 5. Repeat until convergence                         │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
         │
         ↓
┌──────────────────┐
│  LEARNED WEIGHTS │     Header:  0.881
│  (Output)        │     Body:    0.692
│                  │     Malware: 0.376
└──────────────────┘

KEY INSIGHT: Weights reflect which models were most
             predictive in the training data
```

---

## SLIDE LAYOUT OPTION 3: Side-by-Side Comparison

```
┌────────────────────────────────────────────────────────────┐
│ TRAINING PROCESS: FROM DATA TO WEIGHTS                     │
└────────────────────────────────────────────────────────────┘

WHAT WE PROVIDED              WHAT THE ALGORITHM LEARNED
┌────────────────────┐        ┌────────────────────────┐
│ TRAINING DATA:     │        │ OPTIMAL WEIGHTS:       │
│                    │        │                        │
│ 10 labeled emails  │   →    │ • Header:  0.881      │
│ with scores +      │  ML    │ • Body:    0.692      │
│ true labels        │  Magic │ • Malware: 0.376      │
│                    │        │                        │
│ Example:           │        │ WHY THESE VALUES?      │
│ e1: [.81,.67,.92]→1│        │                        │
│ e2: [.10,.22,NA]→0 │        │ Header analysis was    │
│                    │        │ most predictive of     │
│                    │        │ true labels in         │
│                    │        │ training data          │
└────────────────────┘        └────────────────────────┘

ALGORITHM USED: Maximum Likelihood Estimation
METHOD: Gradient Descent Optimization
RESULT: Data-driven weights (not manually tuned)
```

---

## RECOMMENDED SLIDE LAYOUT: Clean & Visual

```
═══════════════════════════════════════════════════════════
              HOW WERE THE WEIGHTS LEARNED?
═══════════════════════════════════════════════════════════

THE TRAINING PROCESS:

┌─────────────────────────────────────────────────────────┐
│ 1️⃣ TRAINING DATA (10 labeled emails)                    │
│                                                          │
│    email_id  |  header  |  body  |  malware  |  Label  │
│    ───────────────────────────────────────────────────  │
│       e1     |   0.81   |  0.67  |   0.92    |    1    │
│       e2     |   0.10   |  0.22  |    NA     |    0    │
│       ...    |   ...    |  ...   |   ...     |   ...   │
└─────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────┐
│ 2️⃣ MACHINE LEARNING ALGORITHM                           │
│                                                          │
│    Scikit-learn Logistic Regression finds weights       │
│    that MAXIMIZE prediction accuracy on training data   │
│                                                          │
│    • Uses Maximum Likelihood Estimation                 │
│    • Gradient descent optimization                      │
│    • Iteratively adjusts until convergence              │
└─────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────┐
│ 3️⃣ LEARNED WEIGHTS (Emerged from data)                  │
│                                                          │
│    ████████████████████  Header:  0.881  (Highest)     │
│    ██████████████        Body:    0.692                 │
│    ████████              Malware: 0.376  (Lowest)       │
│                                                          │
│    ✓ Header proved most predictive in training data    │
│    ✓ NOT manually tuned - discovered automatically     │
└─────────────────────────────────────────────────────────┘

KEY TAKEAWAY: Weights are DATA-DRIVEN, not arbitrary
```

---

## TALKING POINTS FOR THIS SLIDE:

1. **"We don't manually set these weights"**
   - They emerge from training on labeled examples
   - Scikit-learn's algorithm finds optimal values

2. **"Training data: 10 labeled emails"**
   - Each has three model scores + true label
   - Security analysts labeled them as malicious/benign

3. **"Maximum Likelihood Estimation"**
   - Statistical method to find best-fit parameters
   - Iteratively adjusts weights to maximize accuracy

4. **"Header weight is highest (0.881)"**
   - Not because we said so
   - Because header analysis was most predictive in training
   - Data tells us which models to trust more

5. **"Production system would use more training data"**
   - Our 10 examples are proof-of-concept
   - Real system: hundreds or thousands of labeled emails
   - Retrain periodically as threats evolve

---

## SIMPLIFIED VERSION (If Time is Limited):

```
HOW WEIGHTS WERE LEARNED

TRAINING DATA → MACHINE LEARNING → WEIGHTS
   (10 emails)    (Scikit-learn)    (0.881, 0.692, 0.376)

• Provided labeled examples (scores + true labels)
• Logistic regression found optimal weights automatically
• Header proved most predictive → highest weight (0.881)
• These emerged from DATA, not manual tuning
```

---

## WHICH LAYOUT TO USE?

- **Option 1 (Step-by-Step):** Best for technical audience
- **Option 2 (Visual Flow):** Best for quick understanding
- **Option 3 (Side-by-Side):** Best for showing transformation
- **Recommended:** Clean & Visual - balances detail with clarity
- **Simplified:** Use if you have <30 seconds for this slide

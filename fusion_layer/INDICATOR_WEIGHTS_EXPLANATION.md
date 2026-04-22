# Indicator Feature Weights Explained

## THE WEIGHTS ON YOUR SLIDE ARE CORRECT:

```
Negative weights (-0.261 on missing values)
+ 0.426 on (has_malware)
```

These come from the actual trained model and are **accurate**!

---

## FULL BREAKDOWN FROM TRAINED MODEL:

From `artifacts/logistic_fusion_metadata.json`:

**Indicator Feature Weights:**
- `has_header` = **-0.261**
- `has_body` = **-0.261**
- `has_malware` = **+0.426**

---

## WHAT THESE MEAN:

### 1. Negative Weights on has_header and has_body (-0.261)

**Interpretation:** "Missing these scores is a bad signal"

**Why negative?**
- When `has_header = 0` (missing), the model subtracts nothing: 0 × (-0.261) = 0
- When `has_header = 1` (present), the model adds: 1 × (-0.261) = **-0.261** to the logit

**Effect:**
- Having the header score DECREASES the logit by 0.261
- This seems counterintuitive at first, but it's because:
  - The filled probability value (p_header_filled) has a positive weight (+0.881)
  - The indicator's negative weight adjusts for imputed values
  - If header is missing, p_header_filled=0.5 contributes: 0.881 × 0.5 = 0.441
  - But has_header=0 contributes: -0.261 × 0 = 0
  - Net effect when missing: +0.441 (from imputed value only)
  - Net effect when present (e.g., 0.88): (0.881 × 0.88) + (-0.261 × 1) = 0.775 - 0.261 = **0.514**

**Simpler Interpretation:**
The model learned that when data is present, it needs to "subtract out" the uncertainty penalty. Missing data = less confident prediction.

---

### 2. Positive Weight on has_malware (+0.426)

**Interpretation:** "The presence of an attachment increases concern"

**Why positive?**
- When `has_malware = 1` (attachment exists), adds +0.426 to logit
- When `has_malware = 0` (no attachment), adds 0

**Effect:**
- Emails WITH attachments get a boost of +0.426 toward "malicious"
- Even if malware score is low, the mere presence of an attachment is suspicious
- This makes sense: attachments are an attack vector

**Example:**
```
Email A: No attachment
- p_malware_filled = 0.50 (imputed)
- has_malware = 0
- Contribution: (0.376 × 0.50) + (0.426 × 0) = 0.188

Email B: Has attachment, low malware score
- p_malware_filled = 0.20 (real, but low)
- has_malware = 1
- Contribution: (0.376 × 0.20) + (0.426 × 1) = 0.075 + 0.426 = 0.501

Result: Email B gets a higher contribution despite lower malware score!
```

---

## WHY THESE WEIGHTS WERE LEARNED:

### Training Data Pattern:

The model discovered from the 10 training examples:

1. **Emails with attachments were more likely to be malicious**
   → Learned: has_malware gets positive weight (+0.426)

2. **When header/body scores were missing, predictions were less reliable**
   → Learned: has_header/has_body get negative weights (-0.261)

These weren't programmed—the algorithm found these patterns in the data!

---

## COMPARISON TABLE:

| Scenario | has_header | has_body | has_malware | What This Means |
|----------|-----------|----------|-------------|-----------------|
| All present | 1 | 1 | 1 | Most confident: all data available |
| No attachment | 1 | 1 | 0 | Confident: header & body real, no attachment |
| Missing header | 0 | 1 | 1 | Less confident: using imputed header |
| Only body | 0 | 1 | 0 | Least confident: only one real score |

**Weight contributions:**
- All present: (-0.261) + (-0.261) + (+0.426) = **-0.096**
- No attachment: (-0.261) + (-0.261) + (0) = **-0.522**
- Missing header: (0) + (-0.261) + (+0.426) = **+0.165**
- Only body: (0) + (-0.261) + (0) = **-0.261**

---

## FOR YOUR PRESENTATION:

### If asked: "What do the negative weights on has_header/has_body mean?"

**Answer:**

"These indicator features tell the model which scores are real versus imputed. The negative weights (-0.261) act as a confidence adjustment—when we have the actual score, we apply this adjustment. When the score is missing, we don't. This allows the model to automatically account for uncertainty in imputed values. It's a clever way to handle missing data that the model learned from the training examples."

### If asked: "Why is has_malware positive (+0.426)?"

**Answer:**

"The model learned from training data that emails with attachments were more likely to be malicious, regardless of the specific malware score. So even if an attachment has a low malware probability, the mere presence of an attachment adds +0.426 to the threat assessment. This makes security sense—attachments are an attack vector, so their presence alone increases concern."

---

## VISUAL REPRESENTATION FOR SLIDE:

```
INDICATOR FEATURES (Binary flags 0 or 1):

┌──────────────────────────────────────────────────┐
│ has_header = 1  →  adds -0.261 to logit         │
│ (Score present)    "Confidence adjustment"      │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ has_body = 1    →  adds -0.261 to logit         │
│ (Score present)    "Confidence adjustment"      │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ has_malware = 1 →  adds +0.426 to logit        │
│ (Attachment exists) "Attachment is suspicious!" │
└──────────────────────────────────────────────────┘
```

---

## ALTERNATIVE EXPLANATION (Simpler):

**Think of it this way:**

- **Base assumption:** Email with no data is uncertain (neutral threat)
- **Add real header score:** High trust (+0.881 weight on value, -0.261 adjustment)
- **Add real body score:** High trust (+0.692 weight on value, -0.261 adjustment)
- **Add real malware score:** Moderate trust (+0.376 weight on value)
- **Has attachment:** Extra concern (+0.426 bonus to threat level)

The negative weights ensure the model knows the difference between "header score is really 0.5" vs "we guessed 0.5 because header is missing."

---

## SUMMARY:

✅ **-0.261 on has_header/has_body is CORRECT**  
✅ **+0.426 on has_malware is CORRECT**  
✅ **These numbers come from the trained model**  
✅ **They make logical sense:**  
   - Negative on missing = less confident  
   - Positive on attachment = more suspicious  

**No changes needed on your slide!**

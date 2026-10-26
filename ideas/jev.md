# JEV - open-source deterioration risk model

Probability that a waiting patient gets worse soon. One part of the score (queue.md), never the whole order.
Open source: our own code, training script, trained weights and metrics live in this repo; open libraries only (scikit-learn), no closed model or paid API, anyone can retrain it from the dataset.

## Input

One row per request, computed as of a date (no future leakage). Exact list: MODEL_FEATURES in data/build_features.py (54).

- Patient: age, sex, ASA, comorbidities (DM2, ICC, ischemic heart disease, DPOC, DRC, anticoagulation, AF, obesity, smoking)
- Diagnosis: oncologic by CID, uncertain CID, urgent CID, positive biopsy
- Procedure: risco_cirurgico, porte, necessita_uti
- Status: pain, limitation (+ missing flags)
- Events in 30/90/180 days: ER, hospitalizations, imaging progression, re-evaluation worse, reported worsening, no-shows, HbA1c and trend
- Time: days in queue, days since last review
- Text signals from the agents (agents.md), as booleans

Kept out: name and ids, municipality and distance (equity), manual priority and flags (baseline only), pre-op fields.

## Label

No outcomes in the dataset, so a proxy: features as of (reference date - 90 days), label = worsening event within 90 days.
out/train_h90.csv: 734 rows, 158 positives (22%). Caveat: worsening events cluster near the reference date, so the model leans on static features.

## Model

- Regularized logistic regression, ~20 features (what 158 positives support); coefficients are auditable and go on the receipt.
- Backtest: features as of a past date, check who actually worsened after it. precision@k and AUC vs the manual priority.
- Ship: train script + saved model + a short model card (data, features, metrics, limits) in the repo.

# Priority queue structure

How the queue is built, stored and served. The engine is deterministic: same events + same policy = same order.
Agents and JEV feed it (agents.md, jev.md); they never reorder it directly.

## Data model

| Table | What it holds |
|---|---|
| requests | One row per active solicitacao (fila_cirurgica.csv after cleaning) |
| events | Append-only log: eventos_clinicos.csv + new events posted to the API |
| signals | Structured flags extracted from text by the agents, with quoted evidence |
| snapshots | The ordered queue as of a date + policy version: position, tier, score, receipt |
| proposals | Tier changes / alerts waiting for the regulator: who proposed, evidence, status, who decided, when |

Recompute on every new event (that request only) and rebuild the whole queue on demand "as of" any date.

## Step 0 - clean (done: data/build_features.py)

- Normalize CID (upper, no dot), priority spelling, municipality.
- Merge 22 duplicate requests into the earliest (move events and text). 5 of the dropped are oncologic: list them in DECISOES.md, the verifier warns.
- Remove 24 that left the queue (gave up, operated elsewhere, found in observacoes).
- Drop 9 orphan and 7 duplicated events.
- Rebuild oncologic / diabetic / worsening flags from CID, events and text. Manual flags and prioridade_regulacao are only the baseline to beat.
- Result: 895 active requests.

## Layer 1 - tiers (SWALIS-based hard rules)

| Tier | Max wait | Rule |
|---|---|---|
| A1 | 15 days | C* + progression sign (imaging progression, ER, hospitalization, alarm text); urgent CIDs I20.0, K40.0, K40.3, K42.0, K43.0, K80.0, N13.2, I83.2; life-threatening text |
| A2 | 21 days | Any other C*; positive biopsy with benign/uncertain CID; uncertain CID (D37-D48, R91) with suspicious text |
| B | 60 days | Pain >= 7, severe limitation, recent ER/hospitalization, functional alarm text |
| C | 180 days | Moderate pain or limitation |
| D | 360 days | Little or no pain or limitation |

## Layer 2 - score 0-100 inside a tier

    score = w1*severity + w2*deterioration + w3*time_pressure + w4*jev_risk + w5*frailty

- severity: risco_cirurgico, pain, limitation
- deterioration: worsening events in 30/90/180 days
- time_pressure: days waited / tier max wait, convex past 1
- jev_risk: JEV probability (jev.md)
- frailty: age, ASA, comorbidities
- ties: entry date (FIFO)

## Invariants (checked on every snapshot)

- Golden rule: no C* below a patient without clinical urgency. Holds by construction (every C* is A1/A2), and the guard agent re-checks it; a snapshot that fails is not published.
- Moving a patient down is only a proposal with a justification, for the regulator to confirm. Never a C*.
- Tier changes are proposals until the regulator confirms. The regulator can override a position with a written reason. Everything is logged.

## Explainability

Every position has a receipt: tier and why, each score part, events that moved it, policy version.
The justificativa column comes from a deterministic template on the receipt, e.g.
"A2 (neoplasia maligna C50.9); 3 meses na fila (prazo 21 dias); PS em 10/2026; risco JEV 0.41".

## Backend

Python, pandas, FastAPI, SQLite. Engine is a standalone module: features -> tiers -> score -> snapshot -> receipts.

- GET  /queue?asof=YYYY-MM-DD&policy=v1   ordered queue
- GET  /requests/{id}?asof=...             receipt, events, signals, proposals
- POST /events                              new event -> recompute -> agents run
- GET  /proposals?status=pending            regulator's inbox
- POST /proposals/{id}/decision             confirm / reject with a reason
- GET  /export/fila_priorizada.csv          the deliverable (solicitacao_id, posicao, justificativa)

Check the deliverable: python data/dataset/verificar_fila_priorizada.py fila_priorizada.csv

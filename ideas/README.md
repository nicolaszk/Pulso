# Pulso - ideas

Desafio 1: Priorizacao Inteligente da Fila Cirurgica (9a Hackatona, Fin-x, PUCRS, Hospital Sao Lucas).
Who should operate first, and how do we defend that answer?

    ROADMAP.md     what we build, in order, with deadlines
    queue.md       structure of the priority queue: data model, tiers, score, invariants, backend API
    jev.md         JEV, our open-source deterioration risk model
    agents.md      agents monitoring the queue and proposing changes
    data/          build_features.py (cleaning + features) and the dataset as provided

## The challenge, what matters

- Prioritization only. Room scheduling, pre-op and cancellations are out of scope.
- Works on the whole dataset (941 requests, ~1,500 events, synthetic, reference date 23/10/2026).
- Every decision is explainable and the human has the last word: the solution proposes, the professional decides.
- Golden rule: no CID C* patient below a patient without clinical urgency. Use the CID, not the flag. Breaking it = not evaluated.
- Demotions: only suggested, with a justification, for the regulator to confirm. Never a C*.
- Free stack; LLM APIs allowed with our own keys.

Deliverables: public repo with event commit history, README that runs on a clean machine, DECISOES.md (approach, user, why, what was left out on purpose), working solution, fila_priorizada.csv (solicitacao_id, posicao, justificativa), 5-minute pitch.
Judging: value for the decision maker 30%, originality 30%, safety and explainability 20%, technical execution 20%.

## Run

From this folder:

    pip install -r data/requirements.txt
    python data/build_features.py
    python data/dataset/verificar_fila_priorizada.py fila_priorizada.csv

build_features.py writes to out/ (git-ignored): features.csv (895 active), removed.csv (46), train_h90.csv (JEV training table).

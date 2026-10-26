# Roadmap

Sat 24/10. Deadlines: fila_priorizada.csv 14:00, repo public 18:00, pitch 19:00.
Rule: always keep a working end-to-end ordering, then improve it.
Primary user (assumed): the regulator. Every change the system proposes goes to them.

| # | Step | Done when | Doc |
|---|---|---|---|
| 0 | Clean data + features | build_features.py -> 895 active requests | queue.md |
| 1 | Priority queue v1: tiers + score, fixed weights | fila_priorizada.csv passes the verifier (by 14:00) | queue.md |
| 2 | Backend: event log, snapshots, proposals, API | POST an event -> queue recomputes -> proposal appears | queue.md |
| 3 | JEV v1 (open source) | trained, backtested vs manual priority, feeds predicted_risk | jev.md |
| 4 | Monitoring agents | text reader + watchers write proposals with evidence; golden-rule guard blocks bad snapshots | agents.md |
| 5 | Ship | DECISOES.md, root README runs on a clean machine, repo public (by 18:00) | - |

Stretch, only if 0-5 are done: Monte Carlo ranges on the weights, LLM plain-language explanations.

Out of scope (write it in DECISOES.md): room scheduling, pre-op preparation, cancellations, frontend beyond what the demo needs.

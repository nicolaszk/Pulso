# Agents monitoring the queue

The queue is a stream, not a photo. Agents watch it and propose; the engine orders; the regulator decides.
Agents never change a position. Their output is a signal (with quoted evidence) or a proposal in the regulator's inbox (queue.md).

## When they run

- On every new event (POST /events): agents for that request.
- On a full rebuild / daily sweep: deadline and consistency agents over the whole queue.

## The agents

| Agent | Watches | Produces |
|---|---|---|
| Text reader (LLM) | justificativa_clinica, observacoes, event descriptions | Signals with quoted evidence: obstrucao, infeccao, sangramento, progressao_tumoral, cardiorresp, funcional, suspeita_malignidade, piora, vaga; exits, reported worsening, unreachable. Handles negation ("sem sinais de encarceramento") that regex misses. |
| Deterioration watcher | New ER visit, hospitalization, imaging progression, positive biopsy, HbA1c rising, reported worsening | Proposal to move up a tier, with the events as evidence + alert |
| Deadline watcher | Days waited vs tier max wait | Alert before the deadline; proposal to promote when far past it |
| Consistency auditor | Manual flags vs CID/events, positive biopsy with benign CID, duplicates, exits written only in observacoes | Proposal to fix CID / merge / remove, with evidence |
| Silence watcher | No contact, nao_atendeu, missed appointments | Alert: patient to contact |
| Golden-rule guard | Every new snapshot | Blocks publishing if any C* sits below a patient without clinical urgency |

## Rules

- Text reader output is structured JSON (category, quote, source field), stored in signals and cached, so the order is reproducible.
- Regex stand-ins (txt_*, obs_* in data/build_features.py) use the same names, so swapping in the LLM changes nothing downstream.
- Demotion proposals need a justification and are never made for a C*.
- LLM via API with our own keys (allowed by the rules; data is synthetic).

# Technical Debt Register

Deferred refactors and known debt. Each entry cites the phase/plan that introduced
the debt and the expected resolution timing.

## Open

- **nodes.py split (introduced Phase 6, plan 06-05):** `src/ai_hedge_fund/graph/nodes.py`
  grew to ~910 lines after Phase 6, exceeding CLAUDE.md's 800-line soft cap. Split
  deferred to avoid diff/merge risk against Phase 6 integration tests. Target: Phase 7
  prelude or a dedicated refactor plan — split into `nodes/foundation.py`,
  `nodes/multi_agent.py`, `nodes/debate.py`, `nodes/risk.py` with a re-exporting
  `nodes/__init__.py`. Pure refactor with zero behavior change.

## Closed

_(none yet)_

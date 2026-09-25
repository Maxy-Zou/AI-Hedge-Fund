---
phase: <NN>
slug: <slug>
title: <Title>
milestone: <vX.Y>
requirements: [<REQ-01>, ...]
branch: phase/<NN>-<slug>
status: draft            # draft -> signed-off
signed_off:
written: <YYYY-MM-DD>
---

# Phase <NN> -- <Title>

**Goal** (ROADMAP.md): <one sentence>

**Starting point:** <what previous phases left ready; what this phase needs from the environment>

## Decisions

One line of choice + one line of rationale each. Mark the ones that need the human.

- **D1 -- <choice>.** <why>. **Needs sign-off.**
- **D2 -- <choice>.** <why>. Default; override at sign-off.

## Interfaces

The contracts code depends on -- the part that must stay current. Signatures, Pydantic models,
DDL, CLI flags, error types and when each is raised. No implementation bodies.

```python
def submit(signal_id: int, *, broker: BrokerClient, session: Session) -> SubmitResult: ...
```

## External contracts

| Vendor call | Probed shape / fixture | Source (probe run or doc URL + date) |
|---|---|---|

## Success criteria -> proof

| # | ROADMAP criterion | Proven by (node id or command) |
|---|---|---|

## Tasks

T0 is the scaffold: every shared edit (config fields, error classes, fakes, ORM columns,
migration file, `__init__` exports, dependencies) so later tasks only add new modules.

```yaml phase-tasks
- id: T0
  title: scaffold shared contracts
  owns: [src/ai_hedge_fund/<pkg>/errors.py, tests/<pkg>/fakes.py, src/ai_hedge_fund/config.py]
- id: T1
  title: <leaf task>
  owns: [src/ai_hedge_fund/<pkg>/<module>.py, tests/<pkg>/test_<module>.py]
  reads: [src/ai_hedge_fund/<pkg>/errors.py]
  depends: [T0]
```

Per-task notes (only where the task block isn't self-explanatory):

- **T1** -- <RED tests to write first; edge cases>

## Pre-mortem

Premise: three months on, this phase shipped and something traces back here.
Severity: **C** corrupts data or sends an order that shouldn't exist; **H** silent wrong
behaviour; **M** loud failure.

```yaml phase-premortem
- id: PM1
  severity: C
  failure: <what went wrong, concretely>
  invariant: <rule it violates>
  test: tests/<pkg>/test_<module>.py::test_<name>
```

## Out of scope

- <item> (<where it goes instead>)

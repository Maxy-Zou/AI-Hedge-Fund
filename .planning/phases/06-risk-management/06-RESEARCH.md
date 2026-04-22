# Phase 6: Risk Management - Research

**Researched:** 2026-04-22
**Domain:** Risk-manager agent as a non-overridable veto gate in a LangGraph multi-agent pipeline, with deterministic portfolio-risk calculations (position sizing, sector concentration, correlation, drawdown projection) loaded from a human-editable YAML policy file.
**Confidence:** HIGH (stack, topology, math), MEDIUM (policy thresholds — user discretion), LOW (none material)

## Summary

Phase 6 inserts a single `risk_manager_node` between `debate_synthesis_node` and `signal_node` in `build_debate_pipeline`. The node performs deterministic hard-limit checks via pure-Python tool functions over a `PortfolioState` snapshot loaded from PostgreSQL and a `RiskPolicy` loaded from a YAML file. On any violation, it emits a `RiskAssessment(status="VETOED", ...)` with a named `constraint_violated` and blocks routing to `signal_node` via `add_conditional_edges`. The LLM is used only for an advisory **natural-language rationale** over the deterministic assessment — it NEVER computes position sizes, correlations, drawdowns, or decides the veto. This matches CLAUDE.md's tool-first rule and the documented FinCon, TradingAgents, AlphaAgents risk patterns.

The architecture is almost fully determined by constraints already in the codebase: (a) additive-builder pattern per 05-RESEARCH.md (new `build_risk_pipeline` alongside unchanged `build_debate_pipeline`) or extend-in-place if we accept breaking Phase-5's direct `debate_synthesis -> signal` edge; recommendation below is **extend-in-place with conditional edges** since the debate pipeline was already built understanding that risk would slot in (per Phase-5 summary: "Phase 6 (Risk Management) can begin once UAT passes. The compiled `build_debate_pipeline` is the direct input to Phase 6's risk-manager veto node"); (b) REASONING tier for the advisory-rationale agent (same tier as manager/synthesis); (c) zero tools on the agent itself (all quantitative work is done in deterministic pre-computation and passed into the LLM prompt); (d) schema-enforced `RiskAssessment` with `Literal["APPROVED","VETOED"]` status so downstream routing is type-safe; (e) thin async node wrapper over the agent following the 14-node template already in `graph/nodes.py`.

The only genuinely new decisions are: (1) **PortfolioState schema and loading mechanism** (there is NO existing portfolio/position table — this is net-new); (2) **policy file format** (YAML recommended, consistent with belief-memory's "human-readable YAML/JSON" mandate in MEM-02); (3) **drawdown projection technique** (historical simulation recommended over parametric VaR — captures fat tails, has no normality assumption, and works with the pre-existing `DailyPrice` cache); (4) **correlation window and data source** (60-day rolling daily log-returns from `DailyPrice` cache, same cache + math pattern already used by `data/tools/price_tools.py::_compute_stats`).

**Primary recommendation:** Extend `build_debate_pipeline` in place with a new `risk_manager_node` between `debate_synthesis` and `signal`, using `add_conditional_edges` to route APPROVED -> signal -> END vs. VETOED -> END directly. All risk math is pure-Python in a new `src/ai_hedge_fund/risk/` subpackage (mirrors `data/` and `observability/` organization). Policy loaded from `config/risk_policy.yaml` via a `RiskPolicy` Pydantic model. PortfolioState loaded from a new `portfolio_positions` SQLAlchemy table (append-only; v1 seeded from a config file for paper-portfolio use — no live brokerage). Pydantic `Literal["APPROVED","VETOED"]` on `RiskAssessment.status` is the schema-level enforcement that routing is total and exhaustive.

## User Constraints (from CONTEXT.md)

### Locked Decisions

All implementation choices are at Claude's discretion — discuss phase was skipped per `workflow.skip_discuss=true`. Planner should use:

- ROADMAP phase 6 goal, three success criteria, and RISK-01/02/03 requirement definitions as the spec.
- Phase 4 + Phase 5 patterns (thin async node wrappers, immutable `model_copy(update={...})` overwrite, `get_<role>_limits()`, sequential LangGraph chain, additive builder) as the architectural baseline to extend.
- Existing codebase conventions (tool-first for quant, schema-enforced Pydantic constraints, type hints required, `str | None` union, ruff format/check, functions <50 lines, files <800 lines — `src/ai_hedge_fund/graph/nodes.py` is already 813 lines so splitting may be required).
- CLAUDE.md agent-development rules (tool-first, temporal controls, structured output, token budgets, belief memory human-readable).

### Grounding Guardrails (project-wide, from CONTEXT.md)

- Risk checks must be **deterministic tool calls** — LLMs never compute position sizes, drawdowns, or correlations directly.
- Veto output is structured (pydantic model) with named constraint, observed value, limit, and blocked signal reference.
- Hard limits come from a **human-editable YAML/JSON policy file** (belief-memory-adjacent) — not hardcoded constants.
- Portfolio state is loaded from **PostgreSQL**; append-only history preserved.

### Claude's Discretion

Everything above that is not explicitly locked. Research below makes specific recommendations for each area.

### Deferred Ideas (OUT OF SCOPE per CONTEXT.md + additional context)

- **Live brokerage position retrieval** — paper portfolio only for now (IBKR/Alpaca integration is v2 PAPER-01).
- **Real-time margin/options risk** — use simple notional exposure; options risk handled in OPT-* when options phase arrives.
- **Dynamic risk-limit tuning** — limits are fixed in the policy YAML, edited by human.
- **TradingAgents-style three-debator risk team (Aggressive/Conservative/Neutral)** — interesting but deferred. RISK-01/02/03 only require a single veto-capable Risk Manager; the three-debator pattern would add three new LLM agents and 3x cost without advancing the phase acceptance criteria. See "Alternatives Considered" for rationale.
- **CVaR-based within-episode risk control (FinCon pattern)** — defer to Phase 7 (Memory and Learning). Requires persistent PnL history that v1 paper-portfolio does not have yet.
- **RL-based risk policy tuning** — explicitly out-of-scope per REQUIREMENTS.md (FLAG-Trader/Trading-R1 excluded).

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RISK-01 | Risk Manager agent with veto power on high-risk recommendations | `risk_manager_node` wrapping `risk_manager_agent` (REASONING tier, zero tools); `RiskAssessment.status: Literal["APPROVED","VETOED"]` schema; LangGraph `add_conditional_edges` from `risk_manager` to `signal` (APPROVED) or `END` (VETOED) — schema + topology together make the veto structurally irreversible. No downstream node can set `status="APPROVED"` after a veto because `risk_manager` is the single writer of the `risk_assessment` field and the routing decision is read-only after that node. |
| RISK-02 | Position sizing constraints enforced as hard limits (not suggestions) | Deterministic `check_position_size(signal, policy)` Python function — invoked BEFORE the LLM runs. If `signal.position_size_pct > policy.max_single_position_pct`, the node sets `RiskAssessment(status="VETOED", constraint_violated="max_single_position_pct", observed=X, limit=Y)` and short-circuits. LLM is not asked to decide — CLAUDE.md tool-first rule. Rejection is REJECTION, not silent capping — the `signal` node is never reached. |
| RISK-03 | Portfolio-level risk checks (sector concentration, correlation, max drawdown thresholds) | Three pure-Python functions in `src/ai_hedge_fund/risk/portfolio.py`: `check_sector_concentration(portfolio, candidate, policy)`, `compute_correlation_with_portfolio(candidate, portfolio, prices, window_days=60)` + threshold check, `project_max_drawdown(portfolio + candidate, prices, method="historical_simulation")` + threshold check. Each triggers a named `constraint_violated` string on violation. Prices come from the pre-existing `DailyPrice` cache; no new data ingestion. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Position-size hard-limit check (> N% single position) | **Tools (pure Python)** | — | CLAUDE.md: LLMs never compute position sizes. Simple comparison — `signal.position_size_pct > policy.max_single_position_pct` — is arithmetic, not judgment. |
| Sector concentration check | **Tools (pure Python)** | — | Aggregate existing positions by sector + incoming candidate; compare to `policy.max_sector_pct`. Pure arithmetic. |
| Correlation with existing positions | **Tools (pure Python + numpy)** | — | Pearson correlation over daily log-returns. Standard numpy/pandas math — `DailyPrice` cache supplies input. |
| Max drawdown projection | **Tools (pure Python + numpy)** | — | Historical simulation: reconstruct portfolio+candidate hypothetical return series, run cumulative-max drawdown formula. |
| Portfolio-state loading | **Database (SQLAlchemy)** | — | New `portfolio_positions` table + loader function. Append-only writes per CLAUDE.md financial-time-series convention. |
| Policy-file loading | **Config (pydantic + pyyaml)** | — | `yaml.safe_load` → `RiskPolicy.model_validate(dict)`. Human-editable per CONTEXT.md guardrail. |
| Natural-language veto rationale for audit trail | **Agent Logic (PydanticAI)** | — | LLM is given the PRE-COMPUTED deterministic result and writes a short human-readable explanation. Output field on `RiskAssessment` is `rationale: str` — advisory only, cannot change the `status`. |
| Veto routing (APPROVED -> signal, VETOED -> END) | **Orchestration (LangGraph)** | — | `add_conditional_edges` from `risk_manager` reading `state["risk_assessment"]["status"]`. Compile-time static (threat model T-06-XX: no runtime graph modification). |
| Short-circuit on upstream error | **Orchestration (LangGraph)** | — | Same `if state.get("error"): return {}` idiom as the 14 existing nodes. |
| Budget enforcement for rationale agent | **Agent Logic (PydanticAI)** via `UsageLimits` | Orchestration-layer `PipelineBudgetTracker` | `get_risk_manager_limits()` returns REASONING-tier limits with `output_override=4_000` (rationale is short — ≤500 tokens typical); pipeline-total cap via existing tracker. |

## Standard Stack

### Core

| Library | Version (verified) | Purpose | Why Standard |
|---------|---------------------|---------|--------------|
| langgraph | 1.1.6 | `add_conditional_edges` for APPROVED/VETOED routing | [VERIFIED: `uv pip show langgraph` 2026-04-22] Already the stack's orchestration layer; `add_conditional_edges` is the documented pattern for veto gates. |
| pydantic-ai | 1.80.0 | `risk_manager_agent` (advisory rationale) with typed output | [VERIFIED: `uv pip show pydantic-ai` 2026-04-22] Already the stack's agent layer; `Agent[None, RiskAssessment]` follows the same shape as `manager_agent`, `debate_synthesis_agent`. |
| pydantic | 2.12.5 | `Literal["APPROVED","VETOED"]` for type-safe routing; `RiskPolicy` schema validation | [VERIFIED: `uv pip show pydantic` 2026-04-22] Schema-level enforcement of status values prevents typos in conditional-edge mapping. |
| pyyaml | 6.0.3 | Load human-editable `risk_policy.yaml` | [VERIFIED: `uv pip show pyyaml` 2026-04-22] Transitive dep (via `langchain`); no new direct dep needed. Standard approach per [pydantic-yaml pattern](https://betterprogramming.pub/validating-yaml-configs-made-easy-with-pydantic-594522612db5). |
| numpy | 2.4.4 | Log-returns, correlation, cumulative-max drawdown math | [VERIFIED: `uv pip show numpy` 2026-04-22] Transitive dep (via `pandas`, `yfinance`); standard numerical stack. |
| pandas | 3.0.2 | Time-series alignment across tickers for correlation | [VERIFIED: `uv pip show pandas` 2026-04-22] Already installed via `yfinance`. `pd.DataFrame.corr()` on aligned log-returns is the standard implementation. |
| sqlalchemy | >=2.0.49 | New `portfolio_positions` table + loader | [VERIFIED: pyproject.toml] Already in stack; follows `DualTimestampMixin` + append-only pattern from existing 6 models. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.0.0+ | `risk_manager_complete` and `risk_manager_veto` log events | [VERIFIED: pyproject.toml] Every node logs a `_complete` event with token counts; veto events additionally log `constraint_violated`, `observed`, `limit`. |
| pytest-asyncio | 1.0+ | Async test fixtures for node + pipeline tests | [VERIFIED: pyproject.toml `asyncio_mode = "auto"`] Already configured. |
| alembic | 1.18.0+ | Migration for new `portfolio_positions` table | [VERIFIED: pyproject.toml] Already in stack; one new revision file. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| YAML policy file | JSON policy file | YAML wins on human-readability (comments, multi-line strings, no quote noise). MEM-02 already mandates "human-readable YAML/JSON" for belief memory; YAML for policy aligns. Pydantic validates both identically. **Recommendation: YAML.** |
| Single Risk Manager agent | TradingAgents-style three-debator team (Aggressive / Conservative / Neutral + Portfolio Manager synthesizer) | TradingAgents' three-debator architecture adds expressiveness but also 3x LLM cost and longer pipelines. [CITED: [TradingAgents paper](https://arxiv.org/abs/2412.20138)] Phase 6 success criteria require only a veto-capable risk manager, not multi-perspective deliberation. FinCon uses a single manager + CVaR triggers. [CITED: [FinCon NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/f7ae4fe91d96f50abc2211f09b6a7e49-Paper-Conference.pdf)] **Recommendation: single agent for v1; three-debator pattern is a future extension if the debate-quality signal warrants it.** |
| Historical simulation for drawdown | Parametric VaR (normal assumption) | Parametric VaR is fast and closed-form but assumes normal returns — an assumption financial data violates (fat tails, skew). [CITED: [Spanish Review of Financial Economics VaR methodologies](https://www.elsevier.es/en-revista-the-spanish-review-financial-economics-332-articulo-a-comprehensive-review-value-at-S217312681300017X)] Historical simulation captures actual fat tails + skew and imposes no distribution assumption. Tradeoff: historical simulation is "limited to scenarios that have already occurred" — our 60-252 day window gives enough coverage for paper-portfolio use. **Recommendation: historical simulation for v1; parametric as an additional sanity check is cheap to add later.** |
| Extend `build_debate_pipeline` in place | Build a new `build_risk_pipeline` (additive, Phase 5 pattern) | Phase-5's Option B was additive because the (manager, signal) direct edge would have formed a diamond with the new debate chain. For Phase 6 there is NO diamond risk: `debate_synthesis -> signal` becomes `debate_synthesis -> risk_manager -> {signal, END}`. Extending in place keeps one "production" pipeline. **Recommendation: extend in place with conditional edges.** The Phase-5 summary already notes: "the compiled `build_debate_pipeline` is the direct input to Phase 6's risk-manager veto node." |
| LLM decides the veto | Deterministic Python decides; LLM writes rationale | CLAUDE.md tool-first rule. An LLM-authored veto would be non-reproducible, prone to sycophancy (agreeing with high-conviction signals), and untestable with deterministic fixtures. **Recommendation: deterministic decision, advisory rationale.** |
| `add_conditional_edges` with state-based routing | LangGraph `interrupt` for human-in-the-loop veto | `interrupt` is for human review (Phase 8 SIG-03). Phase 6 is automated hard-limit checking — must run without human intervention. **Recommendation: conditional_edges.** |
| Correlation window = 252 days (~1 yr) | Correlation window = 60 days (~3 mo) | 252 days matches existing `price_tools._compute_stats` default; 60 days is more responsive to regime changes (correlations rise during crises). Paper-portfolio v1 is not sensitive enough to justify the extra complexity of a regime-dependent window. **Recommendation: 60-day default in policy, configurable via `correlation_window_days`.** Standard industry compromise per [risk-mgmt literature](https://www.risk.net/). |
| Store PortfolioState in PostgreSQL | Store in a YAML file alongside risk_policy.yaml | Portfolio state is transactional (adds, closes, trims) and must be append-only for audit. A YAML file cannot represent append-only history. PostgreSQL via existing SQLAlchemy + `DualTimestampMixin` pattern is the right fit. **Recommendation: PostgreSQL table.** |

**Installation:** No new direct dependencies. pyyaml, pandas, numpy are all already installed as transitive deps.

**Version verification commands:**
```bash
uv pip show langgraph       # 1.1.6  [VERIFIED 2026-04-22]
uv pip show pydantic-ai     # 1.80.0 [VERIFIED 2026-04-22]
uv pip show pydantic        # 2.12.5 [VERIFIED 2026-04-22]
uv pip show pyyaml          # 6.0.3  [VERIFIED 2026-04-22]
uv pip show pandas          # 3.0.2  [VERIFIED 2026-04-22]
uv pip show numpy           # 2.4.4  [VERIFIED 2026-04-22]
```

## Architecture Patterns

### System Architecture Diagram (Phase-6 extension of Phase-5 debate pipeline)

```
DebatePipelineState (+ risk_assessment field)
       |
       v
  START (ticker, as_of_date)
       |
       +---> fundamental_node  --+
       +---> sentiment_node    --+--> [operator.add on analyst_reports]
       +---> technical_node    --+          |
                                            v
                                     manager_node
                                            |
                                            v
                                      bull_node
                                            |
                                            v
                                      bear_node
                                            |
                                            v
                                    rebuttal_node
                                            |
                                            v
                                final_arguments_node
                                            |
                                            v
                               debate_synthesis_node
                                            |
                                            v
                              +---  risk_manager_node ---+
                              |  (pre-computes 4 checks, |
                              |   then calls LLM for     |
                              |   rationale only)        |
                              |                          |
                              v                          v
              [status=="APPROVED"]              [status=="VETOED"]
                              |                          |
                              v                          v
                        signal_node                     END
                              |                    (no signal; audit trail
                              v                     in state["risk_assessment"])
                             END
```

Data flow:
1. Debate synthesis produces `state["thesis"]` (revised) and `state["debate_synthesis"]`.
2. `risk_manager_node` reads the implied `signal` via a projection: direction + conviction imply a `position_size_pct` target (from Phase-8-ish signal conversion — but for Phase 6 we do NOT run `signal_node` first, so the node computes the **candidate** size from `thesis.confidence` + a policy rule like "high conviction = max_single_position_pct * 1.0, medium = * 0.5, low = * 0.25").
3. Node loads `PortfolioState` from PostgreSQL (current paper positions).
4. Node loads `RiskPolicy` from YAML (cached on module import; reloaded per run is also acceptable at this scale).
5. Node runs the four deterministic checks in order: position size → sector concentration → correlation → drawdown. First violation wins — sets `constraint_violated` to that name.
6. If no violation, node runs `risk_manager_agent` to produce a short `rationale` string; `status` is hard-set to "APPROVED" in Python, NOT by the LLM.
7. If a violation occurred, node runs `risk_manager_agent` with the violation context to produce a `rationale`; `status` is hard-set to "VETOED" in Python.
8. Conditional edge reads `state["risk_assessment"]["status"]` and routes.

### Recommended Project Structure

New subpackage `src/ai_hedge_fund/risk/` (mirrors `data/`, `observability/`, `agents/` organization):

```
src/ai_hedge_fund/
├── risk/
│   ├── __init__.py         # re-exports: RiskPolicy, RiskAssessment, check_*, compute_*, load_policy, load_portfolio
│   ├── policy.py           # RiskPolicy Pydantic model + load_policy(path) -> RiskPolicy
│   ├── portfolio.py        # PortfolioState Pydantic model + load_portfolio(db_session, as_of_date) -> PortfolioState
│   ├── checks.py           # check_position_size, check_sector_concentration (pure functions)
│   ├── correlation.py      # compute_correlation_with_portfolio (numpy/pandas)
│   └── drawdown.py         # project_max_drawdown (historical simulation)
├── agents/
│   └── risk_manager.py     # risk_manager_agent + format_risk_context_for_rationale + get_risk_manager_limits
├── schemas/
│   ├── risk.py             # RiskAssessment (Literal status, constraint_violated, observed, limit, rationale)
│   └── state.py            # DebatePipelineState (extended with risk_assessment field — no new builder state)
├── graph/
│   └── nodes.py            # + risk_manager_node (async, follows 14-node template)
│   └── pipeline.py         # build_debate_pipeline extended with risk_manager + conditional_edges
├── db/
│   └── models.py           # + PortfolioPosition (SQLAlchemy, DualTimestampMixin, append-only)
└── config/
    └── risk_policy.yaml    # checked-in defaults; human-editable
```

**Note on file-size budget:** `src/ai_hedge_fund/graph/nodes.py` is already 813 lines (CLAUDE.md soft limit is 800). Adding `risk_manager_node` will push it over. **Recommendation: during Phase 6, split `nodes.py` into `nodes/foundation.py`, `nodes/multi_agent.py`, `nodes/debate.py`, `nodes/risk.py`, with `nodes/__init__.py` re-exporting the 15 functions for import-path compatibility.** This is a refactor that the planner should evaluate — if split is risky mid-phase, alternative is to accept a single 900+ line file and defer split to a refactor plan. The 800-line limit is a soft recommendation, not a strict rule.

### Pattern 1: Conditional-edge veto routing

**What:** After `risk_manager_node` runs, a single routing function reads `state["risk_assessment"]["status"]` and returns the next-node name.

**When to use:** Any binary gate where downstream path depends on a validated enum on state.

**Example:**
```python
# Source: [CITED: docs.langchain.com/oss/python/langgraph/graph-api — "Map Routing Function Output to Nodes"]
from typing import Literal
from langgraph.graph import END, StateGraph

def route_after_risk(state: DebatePipelineState) -> Literal["signal", "__end__"]:
    """Route to signal if approved, END if vetoed. Literal return type
    matches the path_map so a typo causes a type-check error, not a
    silent routing bug."""
    assessment = state.get("risk_assessment")
    if assessment is None:
        # Upstream error or short-circuit — treat as vetoed (fail-closed).
        return "__end__"
    return "signal" if assessment["status"] == "APPROVED" else "__end__"

builder.add_conditional_edges(
    "risk_manager",
    route_after_risk,
    {"signal": "signal", "__end__": END},
)
```

**Critical detail:** Use `Literal["signal", "__end__"]` as the return annotation AND a path_map dict. Without the path_map, LangGraph treats the string returned as the literal node name — which means a routing function bug (typo, forgotten case) silently routes to a non-existent node or, worse, an unintended node. The path_map makes the mapping explicit and reviewable.

### Pattern 2: Deterministic-first, LLM-advisory

**What:** Pre-compute the decision in Python BEFORE invoking the LLM. The LLM only produces a human-readable rationale; the `status` field is overwritten in Python via `model_copy(update={...})` — same pattern as `debate_synthesis_node` overwriting `quality_score` and `pre_debate_confidence`.

**When to use:** Any high-stakes gate where the outcome must be reproducible, auditable, and testable with deterministic fixtures — i.e., risk, compliance, and safety decisions.

**Example:**
```python
# Source: [CITED: src/ai_hedge_fund/graph/nodes.py::debate_synthesis_node — "Overwrites LLM values with deterministic / authoritative ones"]
async def risk_manager_node(state: DebatePipelineState) -> dict:
    if state.get("error"):
        return {}
    thesis = state.get("thesis")
    if thesis is None:
        return {"error": "No thesis available for risk check"}

    # Deterministic pre-computation — DOES NOT call the LLM.
    policy = load_policy()   # cached
    portfolio = load_portfolio(db_session, as_of_date=state["as_of_date"])
    candidate_size_pct = derive_candidate_size_pct(thesis, policy)
    violation = run_all_checks(thesis, candidate_size_pct, portfolio, policy)
    status = "VETOED" if violation else "APPROVED"

    # LLM produces advisory rationale only.
    prompt = format_risk_context_for_rationale(
        thesis=thesis, status=status, violation=violation,
        portfolio=portfolio, policy=policy,
    )
    try:
        limits = get_risk_manager_limits()
        result = await risk_manager_agent.run(prompt, usage_limits=limits)
    except UsageLimitExceeded as e:
        logger.error("risk_manager_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Risk manager budget exceeded: {e}"}

    # Overwrite LLM status/constraint fields with deterministic ones (tool-first).
    assessment = result.output.model_copy(update={
        "status": status,
        "constraint_violated": violation.name if violation else None,
        "observed": violation.observed if violation else None,
        "limit": violation.limit if violation else None,
    })

    logger.info(
        "risk_manager_complete" if status == "APPROVED" else "risk_manager_veto",
        ticker=state["ticker"],
        status=status,
        constraint_violated=assessment.constraint_violated,
        observed=assessment.observed,
        limit=assessment.limit,
    )
    return {"risk_assessment": assessment.model_dump()}
```

### Pattern 3: YAML-loaded Pydantic policy

**What:** Policy defined as a `BaseModel` subclass. Load with `yaml.safe_load` then `RiskPolicy.model_validate(data)`. Validation at load-time surfaces bad configs as `ValidationError` before the pipeline runs.

**Example:**
```python
# Source: [CITED: https://betterprogramming.pub/validating-yaml-configs-made-easy-with-pydantic-594522612db5]
from pathlib import Path
import yaml
from pydantic import BaseModel, Field

class RiskPolicy(BaseModel):
    max_single_position_pct: float = Field(ge=0.0, le=100.0, description="Hard cap on any one position")
    max_sector_pct: float = Field(ge=0.0, le=100.0, description="Hard cap on any one sector")
    max_total_exposure_pct: float = Field(ge=0.0, le=100.0, description="Sum of all long exposure")
    max_correlation_with_portfolio: float = Field(ge=0.0, le=1.0, description="Max Pearson corr with any existing position")
    max_projected_drawdown_pct: float = Field(ge=0.0, le=100.0, description="Historical-simulation drawdown cap")
    correlation_window_days: int = Field(ge=20, le=504, default=60)
    drawdown_window_days: int = Field(ge=60, le=504, default=252)
    excluded_instrument_types: list[str] = Field(default_factory=list)
    excluded_sectors: list[str] = Field(default_factory=list)

def load_policy(path: Path | str = "config/risk_policy.yaml") -> RiskPolicy:
    text = Path(path).read_text()
    data = yaml.safe_load(text)
    return RiskPolicy.model_validate(data)
```

### Pattern 4: Historical-simulation drawdown

**What:** Given daily log-returns for every ticker in the (portfolio ∪ candidate) position list and their weights, construct the weighted portfolio return series, compute cumulative returns, then cumulative-max-minus-current to get drawdown at each day. Max drawdown = min of that series.

**Example:**
```python
# Source: [CITED: https://felipeczar.medium.com/calculation-drawdown-with-python-c3a761b9f7d8 and https://github.com/quantopian/pyfolio/blob/master/pyfolio/timeseries.py]
import numpy as np
import pandas as pd

def project_max_drawdown_pct(
    weights: dict[str, float],         # ticker -> weight (sum ~ 1.0 for long-only)
    returns: pd.DataFrame,             # columns=tickers, index=trading_date, values=daily log returns
) -> float:
    """Historical-simulation max drawdown over the returns window.

    Returns a positive percentage (e.g., 15.3 means a 15.3% peak-to-trough drop
    occurred during the window when the portfolio held these weights).
    """
    aligned = returns[list(weights)].dropna()
    weight_vec = np.array([weights[t] for t in aligned.columns])
    port_daily_ret = (aligned.values @ weight_vec)  # shape (n_days,)
    equity_curve = np.cumprod(1.0 + port_daily_ret)
    running_max = np.maximum.accumulate(equity_curve)
    drawdown = (running_max - equity_curve) / running_max
    return float(np.max(drawdown) * 100.0)
```

### Pattern 5: 60-day rolling-window correlation check

**Example:**
```python
# Source: [CITED: pandas.pydata.org/docs/reference/api/pandas.DataFrame.corr.html]
def compute_max_correlation_with_portfolio(
    candidate_ticker: str,
    portfolio_tickers: list[str],
    returns: pd.DataFrame,             # daily log returns, all tickers aligned
) -> tuple[str, float]:
    """Return (highest_corr_ticker, correlation_value) from the portfolio.

    Uses Pearson correlation on daily log returns over the aligned window.
    Caller compares this to policy.max_correlation_with_portfolio.
    """
    if not portfolio_tickers:
        return ("", 0.0)
    aligned = returns[[candidate_ticker, *portfolio_tickers]].dropna()
    if len(aligned) < 20:  # sanity floor; matches policy.correlation_window_days lower bound
        return ("", 0.0)  # insufficient data — treat as zero correlation (fail-safe)
    corrs = aligned.corr()[candidate_ticker].drop(candidate_ticker)
    top_ticker = corrs.abs().idxmax()
    return (top_ticker, float(corrs[top_ticker]))
```

### Anti-Patterns to Avoid

- **LLM-authored veto decision:** Never ask the LLM whether to veto. Violates CLAUDE.md tool-first rule. The LLM produces rationale; Python produces the boolean.
- **Silent size-capping:** If a signal requests 15% allocation and policy allows 10%, REJECT with `constraint_violated="max_single_position_pct"`. Do NOT silently rewrite to 10% — that makes the veto invisible to the auditor and contradicts success criterion 2.
- **Hardcoded thresholds:** `max_single_position_pct` and all others live in `risk_policy.yaml`, NOT as Python constants. Changing a limit should require editing YAML, not shipping a code change.
- **Optional risk_assessment field treated as "approved":** If `state.get("risk_assessment") is None`, the route function MUST fail-closed (route to END), NOT fall through to signal. Missing assessment means something went wrong — never default-approve.
- **Recomputing portfolio state from scratch every run:** Query once at the start of `risk_manager_node`. Multiple queries within one node is a distributed-systems smell.
- **Free-form LLM "risk commentary" allowed to change the decision:** The `RiskAssessment` Pydantic schema uses `Literal["APPROVED","VETOED"]` on status; only `rationale: str` is free-form. A sycophantic LLM cannot corrupt routing even if its prompt is jailbroken.
- **Correlation or drawdown computed inside the LLM prompt:** All math is Python. The LLM sees pre-computed numbers and thresholds, never raw price series.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rolling correlation matrix | Custom for-loop Pearson | `pandas.DataFrame.corr()` | NaN handling, numerical stability, alignment across tickers with different history lengths. Already in stack. |
| Max drawdown calculation | Custom peak-trough tracker | `numpy.maximum.accumulate` on equity curve | 5-line idiom is battle-tested; pyfolio + empyrical use the same pattern. |
| YAML loading + validation | `open() + yaml.load + manual type checks` | `yaml.safe_load` + `pydantic.BaseModel.model_validate` | `yaml.load` is CVE-prone (arbitrary object instantiation); `safe_load` + Pydantic is the vetted combination. |
| Conditional routing between nodes | Custom dispatcher node that calls `signal_node()` or `END` directly | `graph.add_conditional_edges(node, router_fn, path_map)` | LangGraph's conditional edges are rendered in `graph.get_graph()` output, visible in Langfuse traces, and type-checkable with a `Literal` return annotation. A custom dispatcher hides the branch. |
| Position sizing derivation from conviction | Bespoke mapping inside risk agent | Pure function `derive_candidate_size_pct(thesis, policy) -> float` in `risk/checks.py` | Testable with golden fixtures; planner can swap the rule (e.g., Kelly-criterion) in one place. |
| Sector lookup | Hardcoded string match on company name | Vendor field on `PortfolioPosition` model (user-supplied on position create) — `sector: str` column | Accurate sector classification is nontrivial; the paper-portfolio is seeded with known positions whose sector is already known. A Finnhub `/stock/profile2` call is optional for v1. |
| PostgreSQL position loader | Custom SQL | SQLAlchemy query via `db_session.query(PortfolioPosition).filter(...)` | Same pattern as existing 6 DB models. |

**Key insight:** Every piece of the risk-manager is expressible in 20-40 lines of Python using libraries already in the stack. The complexity is in policy tuning and testability, not in implementation. Custom math on any of the above is a bug-magnet with zero benefit.

## Runtime State Inventory

> Phase 6 is NOT a rename / refactor / migration phase — it adds net-new functionality. The only "migration" aspect is the new `portfolio_positions` SQLAlchemy table (via Alembic revision) and the new `config/risk_policy.yaml` file (checked in with defaults). No existing state needs renaming.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — verified by grep for "risk" / "policy" / "portfolio" in `src/` and `db/models.py`: only the word appears in CLAUDE.md conventions, not as a DB artifact. | **New:** Create `portfolio_positions` table via Alembic revision; seed with paper-portfolio CSV fixture in `tests/fixtures/`. |
| Live service config | None — no external service integration in Phase 6. | None. |
| OS-registered state | None. | None. |
| Secrets / env vars | None — policy is checked-in YAML (not a secret); portfolio is DB (same DATABASE_URL already in config). | None. |
| Build artifacts / installed packages | None. | None. |

## Common Pitfalls

### Pitfall 1: "Advisory rationale" becomes the actual decision

**What goes wrong:** Agent prompt is too flexible ("explain whether this trade is safe"), and the LLM's judgment, not the deterministic computation, ends up gating the pipeline. Over time, developers add heuristics "the LLM should say VETOED if..." and the code path becomes LLM-authored.

**Why it happens:** Convenience. LLM-in-the-loop feels powerful and the deterministic checks feel "too simple."

**How to avoid:**
- `RiskAssessment.status` is set in the NODE via `model_copy(update={"status": ...})` AFTER the agent runs, always overwriting the LLM's value.
- Unit test: `test_status_always_overwritten_from_deterministic_check` — feed a stub agent that always says APPROVED, feed a policy-violating signal, assert final state has `status == "VETOED"`.
- Code review: `grep -c "status" src/ai_hedge_fund/schemas/risk.py` should show `Literal["APPROVED","VETOED"]` exactly once; any other assignment to `status` in the codebase must be the overwrite line.

**Warning signs:** The word "decide" appearing in the risk_manager system prompt. The prompt should say "explain" or "describe", never "decide" or "judge".

### Pitfall 2: Portfolio state staleness creates look-ahead or stale veto

**What goes wrong:** Portfolio loaded once at pipeline start; by the time risk_manager runs, another analysis has added a position and the drawdown projection is wrong.

**Why it happens:** The pipeline is async + checkpointed; parallel runs are expected.

**How to avoid:**
- Load portfolio INSIDE `risk_manager_node`, not at builder time.
- Filter positions by `as_of_date <= state["as_of_date"]` to ensure temporal correctness (CLAUDE.md "strict temporal controls").
- Integration test: run two pipelines concurrently over the same `as_of_date`; both see the same PortfolioState snapshot.

**Warning signs:** `portfolio = load_portfolio(db_session)` at module scope, or in `build_debate_pipeline(...)`.

### Pitfall 3: Empty portfolio edge case — no correlation or drawdown can be computed

**What goes wrong:** First trade ever — portfolio is empty. Correlation function returns 0 (safe), but drawdown function tries to compute `np.cumprod([]) -> array([1.0])`, then runs cumulative-max on a 1-element array, returns 0% drawdown. Now policy check says "projected drawdown 0% <= 30% limit, APPROVED" — but in reality the candidate single position IS the entire portfolio and drawdown on a single stock over the last 252 days might be 40%.

**Why it happens:** Empty-portfolio reasoning isn't symmetric with "portfolio + candidate".

**How to avoid:**
- `project_max_drawdown` operates on the **post-trade portfolio** (existing positions + candidate at candidate's size). If portfolio is empty, post-trade portfolio = {candidate: 100% of available capital}. The function then evaluates the candidate's historical drawdown at full weight.
- Unit test: `test_empty_portfolio_drawdown_evaluates_candidate_only` — empty portfolio + 10% candidate -> drawdown is 10% of candidate's solo drawdown; empty portfolio + 100% candidate -> drawdown is candidate's solo drawdown.

**Warning signs:** `if not portfolio.positions: return 0.0` at the top of drawdown function.

### Pitfall 4: Missing price history for candidate ticker defaults to "no risk"

**What goes wrong:** Candidate ticker is newly IPO'd, `DailyPrice` cache has 10 days of data. Correlation function's `len(aligned) < 20` check returns 0.0 correlation, drawdown function returns a tiny number. Policy check passes. Real risk is high because we have NO data.

**Why it happens:** "Fail-safe" default (0 on missing data) is correct for correlation (no data == no known correlation) but WRONG for drawdown (no data != low risk).

**How to avoid:**
- For drawdown: if insufficient history, set `constraint_violated="insufficient_price_history"` and VETO. Explicit `RiskPolicy.min_history_days: int = Field(ge=20, default=60)`.
- For correlation: 0 is semantically "unknown", but VETO is overkill. Emit a warning log event and proceed.
- Unit test: `test_insufficient_history_vetoes_on_drawdown` with a ticker that has only 15 days in the cache.

**Warning signs:** Drawdown function returns `0.0` or `None` without a VETO path.

### Pitfall 5: Policy reload mid-run causes mid-pipeline rule flip

**What goes wrong:** Human edits `risk_policy.yaml` while a pipeline is running. Next node run reads the new policy. Veto decision is inconsistent with log trail.

**Why it happens:** Policy loaded per node invocation.

**How to avoid:**
- Load policy ONCE per pipeline run, pin it into a local variable at the top of `risk_manager_node`, emit a structlog event with the policy's SHA256 hash so audit trail can correlate decisions to policy snapshots.
- Defer live-reload to a future phase; v1 policy file changes require pipeline restart.
- Unit test: `test_policy_sha_logged_in_risk_manager_complete_event`.

**Warning signs:** `load_policy()` called at multiple points within a single node.

### Pitfall 6: Sector concentration double-counts the candidate

**What goes wrong:** Portfolio has 8% AAPL (Technology sector). Candidate is 7% GOOG (Technology). Current Technology exposure = 8%; naive "new_sector_pct = current + candidate_size" = 15%. But if AAPL and GOOG are both in the portfolio, sector total is 15% — correct. If the check is running PRE-trade, that's the right number. If the check is running POST-trade from an unpersisted staging state, the candidate might already be in portfolio and get counted twice.

**Why it happens:** Ambiguity over whether "portfolio" is pre-trade or post-trade.

**How to avoid:**
- Document convention: `PortfolioState` in Phase 6 is ALWAYS pre-trade (the state before this signal is acted on).
- `check_sector_concentration(portfolio, candidate, policy)` always adds candidate to the sum.
- Unit test: `test_sector_concentration_pre_trade_assumes_candidate_not_in_portfolio`.

**Warning signs:** The word "already" appearing in sector-check logic.

### Pitfall 7: Conditional-edge router fails open on None / missing state

**What goes wrong:** `risk_manager_node` errors, `state["risk_assessment"]` is None. Router function reads `None["status"]` and throws. Or worse, router returns "signal" because a default-true branch wasn't caught.

**Why it happens:** Exception handling + short-circuit idioms can leave partial state.

**How to avoid:**
- Router MUST handle `None` case and fail CLOSED (return END / "vetoed"):
  ```python
  def route_after_risk(state):
      assessment = state.get("risk_assessment")
      if assessment is None:
          return "__end__"  # fail-closed
      return "signal" if assessment["status"] == "APPROVED" else "__end__"
  ```
- Unit test: `test_router_with_none_assessment_fails_closed`, `test_router_with_missing_status_fails_closed`.

**Warning signs:** Router returns "signal" on any exception or default branch.

### Pitfall 8: Veto path leaves state["signal"] == None, downstream consumers assume success

**What goes wrong:** Phase 8 (SIG-*) consumers assume a completed pipeline has a `signal`. On veto, signal is absent, consumer crashes or, worse, silently misinterprets missing signal as "no opportunity" (should be "blocked by risk").

**Why it happens:** Absence != veto.

**How to avoid:**
- Phase 6 convention: on veto, state ends with `signal == None` AND `risk_assessment == {status: "VETOED", ...}`. Downstream consumers MUST check `risk_assessment` before `signal`.
- Integration test: `test_vetoed_pipeline_signal_is_none_but_risk_assessment_is_populated`.

**Warning signs:** Phase-8 planners treat `signal is None` as generic failure.

## Code Examples

Verified patterns from the existing codebase and authoritative sources.

### Example 1: Adding risk_manager to build_debate_pipeline (extend in place)

```python
# Source: [CITED: src/ai_hedge_fund/graph/pipeline.py::build_debate_pipeline — topology extended for Phase 6]
# Source: [CITED: docs.langchain.com/oss/python/langgraph/graph-api — "Map Routing Function Output to Nodes"]
from typing import Literal

def route_after_risk(state: DebatePipelineState) -> Literal["signal", "__end__"]:
    """Fail-closed router: approved -> signal, vetoed or missing -> END."""
    assessment = state.get("risk_assessment")
    if assessment is None:
        return "__end__"
    return "signal" if assessment["status"] == "APPROVED" else "__end__"

def build_debate_pipeline(checkpointer=None) -> CompiledStateGraph:
    builder = StateGraph(DebatePipelineState)
    # ... (unchanged: fundamental, sentiment, technical, manager, bull, bear, rebuttal,
    #      final_arguments, debate_synthesis nodes and edges)
    builder.add_node("risk_manager", risk_manager_node)  # NEW
    builder.add_node("signal", multi_agent_signal_node)

    # ... (unchanged fan-out/fan-in + debate chain edges)

    # CHANGED: debate_synthesis -> risk_manager (was debate_synthesis -> signal)
    builder.add_edge("debate_synthesis", "risk_manager")
    # CHANGED: risk_manager conditional-routes to signal or END
    builder.add_conditional_edges(
        "risk_manager",
        route_after_risk,
        {"signal": "signal", "__end__": END},
    )
    builder.add_edge("signal", END)

    return builder.compile(checkpointer=checkpointer)
```

### Example 2: RiskAssessment schema

```python
# Source: [CITED: src/ai_hedge_fund/schemas/agents.py::SignalOutput — Literal pattern]
from typing import Literal
from pydantic import BaseModel, Field

class RiskAssessment(BaseModel):
    """Output of the risk manager node. status is AUTHORITATIVE — set by
    deterministic Python, NOT the LLM."""
    ticker: str
    status: Literal["APPROVED", "VETOED"] = Field(
        description="Deterministic outcome; the LLM's value for this field is DISCARDED."
    )
    constraint_violated: Literal[
        "max_single_position_pct",
        "max_sector_pct",
        "max_total_exposure_pct",
        "max_correlation_with_portfolio",
        "max_projected_drawdown_pct",
        "excluded_instrument_type",
        "excluded_sector",
        "insufficient_price_history",
    ] | None = Field(default=None, description="Name of the first-violated constraint; None if approved.")
    observed: float | None = Field(default=None, description="Observed value that triggered the veto.")
    limit: float | None = Field(default=None, description="Policy limit that was exceeded.")
    rationale: str = Field(min_length=1, description="Human-readable explanation; advisory, does not affect status.")
    policy_sha: str = Field(description="SHA256 of the RiskPolicy used, for audit.")
```

### Example 3: Drawdown with edge cases handled

```python
# Source: [CITED: https://github.com/quantopian/pyfolio/blob/master/pyfolio/timeseries.py::max_drawdown]
import numpy as np
import pandas as pd
from ai_hedge_fund.risk.policy import RiskPolicy

def project_max_drawdown_pct(
    weights: dict[str, float],
    returns: pd.DataFrame,
    policy: RiskPolicy,
) -> tuple[float, str | None]:
    """Historical-simulation max drawdown.

    Returns (drawdown_pct, error). error is None on success, or one of:
      - "insufficient_price_history" if any ticker has < policy.min_history_days
    """
    for ticker in weights:
        if ticker not in returns.columns or returns[ticker].count() < policy.min_history_days:
            return (0.0, "insufficient_price_history")

    aligned = returns[list(weights)].dropna()
    if len(aligned) < policy.min_history_days:
        return (0.0, "insufficient_price_history")

    weight_vec = np.array([weights[t] for t in aligned.columns])
    port_daily_ret = (aligned.values @ weight_vec)
    equity_curve = np.cumprod(1.0 + port_daily_ret)
    running_max = np.maximum.accumulate(equity_curve)
    drawdown = (running_max - equity_curve) / running_max
    return (float(np.max(drawdown) * 100.0), None)
```

### Example 4: Example risk_policy.yaml

```yaml
# config/risk_policy.yaml — human-editable risk limits for the paper portfolio.
# Change any value here and restart the pipeline; Pydantic validates on load.

# Hard caps
max_single_position_pct: 10.0      # no one position > 10% of portfolio
max_sector_pct: 30.0               # no one sector > 30% of portfolio
max_total_exposure_pct: 100.0      # sum of long positions; paper-portfolio v1 is long-only

# Correlation
max_correlation_with_portfolio: 0.80   # reject if new position correlates > 0.80 with any existing
correlation_window_days: 60

# Drawdown
max_projected_drawdown_pct: 25.0       # reject if historical-simulation drawdown > 25%
drawdown_window_days: 252
min_history_days: 60                   # tickers with less history cannot be evaluated

# Exclusions
excluded_instrument_types: ["OTC", "SPAC"]
excluded_sectors: []                   # list full sector names from portfolio_positions.sector
```

### Example 5: PortfolioPosition SQLAlchemy model

```python
# Source: [CITED: src/ai_hedge_fund/db/models.py::DailyPrice — DualTimestampMixin append-only pattern]
from sqlalchemy import BigInteger, Date, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ai_hedge_fund.db.base import Base, DualTimestampMixin

class PortfolioPosition(Base, DualTimestampMixin):
    """Paper-portfolio position snapshot. Append-only — closing or resizing a
    position writes a NEW row with the new quantity; no UPDATE statements."""
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint("ticker", "as_of_date", name="uq_portfolio_positions_ticker_asof"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    sector: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)   # shares
    cost_basis_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_value_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(20), default="equity")  # equity, OTC, SPAC, ETF
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Free-form LLM "should I trade?" prompt | Deterministic tool checks + LLM advisory rationale | TradingAgents (arxiv 2412.20138, Dec 2024); FinCon (NeurIPS 2024) | Reproducibility, auditability, testability; industry standard |
| Single-shot veto by risk agent | Structured risk team with perspectives (Aggressive/Conservative/Neutral) | TradingAgents (2024-2025) | Deferred to v2 — adds value but not required for Phase 6 success criteria |
| Parametric VaR (assumes normal returns) | Historical simulation (no distribution assumption) | Post-2008 financial crisis regulatory shift | Standard for non-linear portfolios; captures fat tails |
| Within-episode CVaR triggers | Same; now complemented by over-episode belief updates | FinCon (NeurIPS 2024) | Defer CVaR to Phase 7 — requires persistent PnL history |
| Hardcoded policy constants | YAML / JSON policy files + schema validation | Post-MiFID II compliance era | Human-editable audit trail; standard approach in prop trading |

**Deprecated / outdated:**
- LLM computing the numeric veto value directly (pre-TradingAgents era): known to produce sycophantic outputs on high-conviction signals. Superseded by the deterministic-first pattern above.
- Single-round debate with no explicit synthesis: superseded by the 5-act protocol (already implemented in Phase 5).
- Static equal-weighted portfolio drawdown approximation: superseded by true weighted simulation using actual post-trade weights.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 60-day correlation window and 252-day drawdown window are reasonable defaults for paper-portfolio v1 | Standard Stack → Alternatives | Wrong windows produce false positives/negatives on the veto. Mitigated because both are `RiskPolicy` fields the user can edit. |
| A2 | Single Risk Manager agent (vs. three-debator team) satisfies RISK-01 | Standard Stack → Alternatives | Three-debator adds audit richness but not required by acceptance criteria. If human review wants more perspective, future phase can extend. |
| A3 | `PortfolioPosition.sector` is user-supplied on insert (CSV fixture for paper portfolio), not fetched from Finnhub | Don't Hand-Roll | Wrong sector classification leads to wrong concentration checks. Mitigated by human review of the seed CSV and by allowing Finnhub `profile2` call as a future auto-enrichment. |
| A4 | Position size is derived from thesis.confidence via a fixed rule (high=max, medium=0.5*max, low=0.25*max) | Architecture → Data flow step 2 | A different conviction→size mapping might be preferred (Kelly, equal-weight, fixed-dollar). Rule is a pure function — trivial to swap. User should confirm before implementation. |
| A5 | Phase 6 extends `build_debate_pipeline` in place rather than adding `build_risk_pipeline` additively | Alternatives Considered | Breaks Phase-5 pipeline semantics (debate_synthesis no longer directly connects to signal). Phase-5 summary explicitly anticipates this, so low risk. If user prefers additive builder, planner should fork a copy. |
| A6 | Policy YAML is loaded from `config/risk_policy.yaml` (repo-relative) | Project Structure | Different path convention might be preferred (e.g., `.planning/policy/`, `~/.config/`, env-var-driven). Mitigation: make the path a `load_policy(path=...)` argument with a default. |
| A7 | `RiskPolicy.min_history_days = 60` is a reasonable floor for correlation / drawdown data sufficiency | Pitfall 4 | Too strict: healthy recent IPOs get vetoed. Too lax: newly-listed tickers trigger false confidence. Surface in policy YAML so user can tune. |
| A8 | Splitting `graph/nodes.py` is optional (CLAUDE.md 800-line limit is a soft rule) | Recommended Project Structure | If planner decides to split, it is a separate task; if not, nodes.py grows to ~950 lines. Low risk either way. |
| A9 | Paper-portfolio is long-only in v1 (no shorts in initial seed) | Example 4 YAML | `max_total_exposure_pct: 100.0` assumes long-only. Shorts would change the math (gross vs net exposure). Explicit in policy. |

**Action for planner / discuss-phase:** assumptions A3, A4, A6 (sector source, conviction→size rule, policy file path) are the three highest-value decisions to surface to the user before coding begins. A1, A7 (window sizes, min_history) are tunable post-ship without code changes — acceptable as defaults.

## Open Questions

1. **Conviction → candidate position size mapping (A4)**
   - What we know: thesis produces `confidence: int` (0-100); signal produces `position_size_pct: float`. Phase 6 runs BEFORE signal, so the risk node must derive a candidate size from confidence+policy alone.
   - What's unclear: fixed step function? Linear? Kelly-criterion-inspired? User preference unknown.
   - Recommendation: fixed step function for v1 (high→policy.max_single_position_pct, medium→0.5×, low→0.25×). Pure function in `risk/checks.py::derive_candidate_size_pct` — easy to swap later.

2. **Additive vs in-place builder (A5)**
   - What we know: Phase-5 used additive (`build_debate_pipeline` alongside unchanged `build_multi_agent_pipeline`) to avoid diamond. No diamond risk in Phase 6.
   - What's unclear: user preference for pipeline evolution — "one production pipeline that keeps growing" vs "one frozen pipeline per phase."
   - Recommendation: extend in place. Phase-5 summary already anticipates this. Freezing each phase's builder creates test-maintenance burden without benefit once the phases are sequential.

3. **Sector data source (A3)**
   - What we know: No existing sector lookup; `DailyPrice` table has no sector.
   - What's unclear: Finnhub auto-enrich vs. user-supplied CSV on position insert.
   - Recommendation: user-supplied CSV for v1 paper portfolio (small universe). Finnhub `/stock/profile2` wrapper is a separate task for v2 when universe grows.

4. **Policy file path and location (A6)**
   - What we know: CONTEXT.md says "human-editable YAML/JSON policy file (belief-memory-adjacent)" — matching MEM-02.
   - What's unclear: `config/risk_policy.yaml` vs `.planning/policy/...` vs env-var.
   - Recommendation: `config/risk_policy.yaml` (repo-relative, new `config/` directory). Consistent with future `config/belief_memory.yaml` in Phase 7.

5. **When should `risk_manager_node` run — before or after a notional `signal_draft`?**
   - What we know: Pipeline currently goes `debate_synthesis → signal → END`; Phase 6 makes it `debate_synthesis → risk_manager → {signal, END}`. Risk runs BEFORE signal.
   - What's unclear: Would risk-after-signal catch more issues? (e.g., signal might reduce size itself.)
   - Recommendation: risk-before-signal. This matches CONTEXT.md success criterion 2 ("rejected, NOT silently capped") — if signal runs first and sizes down to compliance, the signal looks approved when it was actually oversized.

6. **Policy versioning / audit**
   - What we know: CLAUDE.md emphasizes audit trail (SIG-04 eventually).
   - What's unclear: Should the SHA of the loaded policy be persisted with the RiskAssessment for later compliance review?
   - Recommendation: YES — include `policy_sha: str` field on `RiskAssessment` (already in Example 2). Cheap, load-time hash compute. Phase 8 SIG-04 will thank us.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Everything | ✓ | 3.13 (via `.venv`) | — |
| uv | Package management | ✓ | 0.11.2 | — |
| langgraph | Orchestration / conditional_edges | ✓ | 1.1.6 | — |
| pydantic-ai | risk_manager_agent | ✓ | 1.80.0 | — |
| pydantic | Schema | ✓ | 2.12.5 | — |
| pyyaml | Policy loading | ✓ | 6.0.3 | — |
| numpy | Drawdown / log-returns math | ✓ | 2.4.4 | — |
| pandas | Correlation DataFrame ops | ✓ | 3.0.2 | — |
| sqlalchemy | PortfolioPosition ORM | ✓ | 2.0+ (pyproject spec) | — |
| alembic | Migration for new table | ✓ | 1.18.0+ | — |
| PostgreSQL 16+ | PortfolioPosition storage in production | Ambient via docker-compose.yml; SQLite in-memory for tests (existing conftest.py fixture) | — | Tests already use `sqlite:///:memory:` per `tests/conftest.py`; production uses PostgreSQL via existing checkpointer. No gap. |
| Anthropic API key | risk_manager_agent (REASONING tier, Opus) | Conditional (skipped in dummy-key tests per existing `_has_real_api_key()` helper) | — | All unit and integration tests use `TestModel` from pydantic-ai (same pattern as Phase 5); no real Anthropic calls in pytest. |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ with pytest-asyncio 1.0+ (asyncio_mode=auto) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/test_risk_*.py tests/unit/test_risk_manager_node.py -x -q` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| RISK-01 | Veto is final — "blocked by risk" output with specific constraint violated; no modified recommendation | Integration | `uv run pytest tests/integration/test_risk_pipeline.py::TestVetoIsFinal::test_vetoed_signal_is_none_and_risk_assessment_populated -x` | ❌ Wave 0 |
| RISK-01 | Conditional router fails CLOSED on missing risk_assessment | Unit | `uv run pytest tests/unit/test_risk_routing.py::test_router_with_none_assessment_fails_closed -x` | ❌ Wave 0 |
| RISK-01 | LLM-produced status is ALWAYS overwritten by deterministic Python value | Unit | `uv run pytest tests/unit/test_risk_manager_node.py::test_status_always_overwritten_from_deterministic_check -x` | ❌ Wave 0 |
| RISK-02 | Signal > max_single_position_pct is REJECTED (not silently capped) | Unit | `uv run pytest tests/unit/test_risk_checks.py::TestPositionSize::test_oversize_is_vetoed_not_capped -x` | ❌ Wave 0 |
| RISK-02 | Rejection reason references the specific limit by name | Unit | `uv run pytest tests/unit/test_risk_checks.py::TestPositionSize::test_constraint_violated_name_matches_policy_field -x` | ❌ Wave 0 |
| RISK-03 | Sector concentration > max_sector_pct triggers named violation | Unit | `uv run pytest tests/unit/test_risk_checks.py::TestSectorConcentration::test_exceeds_threshold_triggers_named_violation -x` | ❌ Wave 0 |
| RISK-03 | Correlation > threshold triggers named violation | Unit | `uv run pytest tests/unit/test_risk_correlation.py::test_high_correlation_triggers_veto -x` | ❌ Wave 0 |
| RISK-03 | Projected max drawdown > threshold triggers named violation | Unit | `uv run pytest tests/unit/test_risk_drawdown.py::test_high_drawdown_triggers_veto -x` | ❌ Wave 0 |
| RISK-03 | Golden-value drawdown matches hand-computed reference on fixture | Unit | `uv run pytest tests/unit/test_risk_drawdown.py::test_golden_value_matches_reference -x` | ❌ Wave 0 |
| RISK-03 | Golden-value correlation matches hand-computed reference on fixture | Unit | `uv run pytest tests/unit/test_risk_correlation.py::test_golden_value_matches_reference -x` | ❌ Wave 0 |
| — (infra) | `RiskPolicy` loads from YAML and validates | Unit | `uv run pytest tests/unit/test_risk_policy.py::test_loads_and_validates_yaml -x` | ❌ Wave 0 |
| — (infra) | `PortfolioPosition` loader returns positions <= as_of_date | Unit | `uv run pytest tests/unit/test_portfolio_loader.py::test_filters_by_as_of_date -x` | ❌ Wave 0 |
| — (infra) | `build_debate_pipeline` still compiles after risk_manager insertion | Unit | `uv run pytest tests/unit/test_debate_pipeline_builder.py::test_risk_manager_node_present -x` | ❌ Wave 0 |
| — (infra) | End-to-end APPROVED path: all 11 nodes run, signal is populated | Integration | `uv run pytest tests/integration/test_risk_pipeline.py::TestApprovedPath::test_approved_signal_populated -x` | ❌ Wave 0 |
| — (infra) | End-to-end VETOED path: signal_node never runs | Integration | `uv run pytest tests/integration/test_risk_pipeline.py::TestVetoedPath::test_signal_node_skipped_on_veto -x` | ❌ Wave 0 |
| — (infra) | Empty portfolio edge case — candidate at full weight | Unit | `uv run pytest tests/unit/test_risk_drawdown.py::test_empty_portfolio_evaluates_candidate_only -x` | ❌ Wave 0 |
| — (infra) | Insufficient price history triggers dedicated violation | Unit | `uv run pytest tests/unit/test_risk_drawdown.py::test_insufficient_history_vetoes -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/unit/test_risk_*.py tests/unit/test_risk_manager_node.py tests/unit/test_risk_routing.py tests/unit/test_portfolio_loader.py -x -q`
- **Per wave merge:** `uv run pytest tests/unit/ tests/integration/test_risk_pipeline.py tests/integration/test_debate_pipeline.py -x` (Phase 5 + Phase 6 together, confirming no regression)
- **Phase gate:** Full suite green (`uv run pytest tests/ -x`) before `/gsd-verify-work`

### Wave 0 Gaps

All Phase 6 test files are net-new. Wave 0 should establish:

- [ ] `tests/unit/test_risk_policy.py` — YAML load + Pydantic validation; malformed YAML fails with clear message.
- [ ] `tests/unit/test_portfolio_loader.py` — `load_portfolio(db_session, as_of_date)` temporal filter; empty portfolio case.
- [ ] `tests/unit/test_risk_checks.py` — `check_position_size`, `check_sector_concentration` golden values + edge cases.
- [ ] `tests/unit/test_risk_correlation.py` — `compute_max_correlation_with_portfolio` golden values; insufficient history case.
- [ ] `tests/unit/test_risk_drawdown.py` — `project_max_drawdown_pct` golden values; empty portfolio; insufficient history.
- [ ] `tests/unit/test_risk_manager_node.py` — async contract; short-circuit on upstream error; LLM status overwrite; missing thesis; rationale-agent budget exceeded.
- [ ] `tests/unit/test_risk_routing.py` — `route_after_risk` on APPROVED / VETOED / None assessment / malformed status.
- [ ] `tests/unit/test_debate_pipeline_builder.py` — extend existing file with risk_manager-present assertion and conditional-edge presence.
- [ ] `tests/integration/test_risk_pipeline.py` — full 11-node pipeline with TestModel; approved path; vetoed path; verify Phase-5 integration tests still pass.
- [ ] `tests/fixtures/paper_portfolio.csv` — seed positions for tests.
- [ ] `tests/fixtures/risk_policy_test.yaml` — test policy with tight thresholds for forcing vetos.
- [ ] `tests/fixtures/price_series_fixture.py` — deterministic return series for correlation/drawdown golden tests (constant returns, known drawdown; high-corr pair; low-corr pair).

No framework install needed — pytest, pytest-asyncio are already configured.

## Project Constraints (from CLAUDE.md)

The following directives from `./CLAUDE.md` are load-bearing for Phase 6 planning:

### Mandatory constraints

- **Tool-first for quantitative work.** LLMs NEVER compute financial ratios, run backtests, or calculate position sizes directly. *Consequence:* deterministic Python pre-computes every veto; LLM does rationale only.
- **Strict temporal controls.** Every data input must have a timestamp. RAG retrieval must filter by "available as of analysis date." *Consequence:* `PortfolioPosition` queries filter by `as_of_date`; `DailyPrice` queries same.
- **Structured debate only. No free-form agent chat.** *Consequence:* the advisory-rationale LLM call has a short, structured output (a single string); no dialogue, no clarification loops.
- **Token budgets from day one.** Every agent has a per-run token cap; every pipeline has a total cost cap. *Consequence:* `get_risk_manager_limits()` with `output_override=4_000` for the short rationale.
- **Belief memory is human-readable.** Stored as YAML/JSON, editable by humans. *Consequence:* `risk_policy.yaml` is the policy file; YAML format; Pydantic validated.
- **Append-only for financial time-series.** Never overwrite historical observations. *Consequence:* `PortfolioPosition` never UPDATEs; each change is a new row with `as_of_date`.
- **All timestamps in UTC.** *Consequence:* `PortfolioPosition.as_of_date` is UTC; `DualTimestampMixin` already enforces.
- **Type hints required on all function params and return values.** *Consequence:* every function in `src/ai_hedge_fund/risk/` has full annotations.
- **Functions <50 lines, files <800 lines.** *Consequence:* keep `risk_manager_node` under 50 lines (delegate to helpers); evaluate splitting `graph/nodes.py` if it grows past 800.
- **`from __future__ import annotations`** — *Consequence:* first line of every new module.
- **ruff format + ruff check --fix before every commit.** *Consequence:* standard CI gate.
- **Honest positioning: "LLM-powered research at scale" — not "AI that beats the market".** *Consequence:* docstring on `risk_manager_node` explicitly says the LLM does not compute risk; Python does. README + commit messages use this framing.

### GSD workflow enforcement

- Before using Edit, Write, or other file-changing tools, start work through a GSD command. *Consequence:* all Phase 6 code changes must go through `/gsd-plan-phase` → `/gsd-execute-phase`.

## Security Domain

> `security_enforcement` is enabled by default (absent = enabled in config.json).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No new auth surface in Phase 6 (inherits pipeline's; no external API accepts user input). |
| V3 Session Management | no | LangGraph checkpointer (inherited from Phase 1) handles session state; no new sessions. |
| V4 Access Control | yes | `risk_policy.yaml` is a filesystem artifact — file-system permissions apply. Recommend: docs should note this file should be read-only for the pipeline process, writable only by ops. |
| V5 Input Validation | yes | `yaml.safe_load` (NOT `yaml.load`) for policy file; Pydantic `RiskPolicy.model_validate` after; SQLAlchemy parameterized queries for `PortfolioPosition` loader. |
| V6 Cryptography | yes | `policy_sha` on `RiskAssessment` uses SHA256 via `hashlib` — standard library; never hand-roll. |
| V8 Data Protection | yes | No PII in this phase; portfolio holdings are non-secret internal data; policy YAML is not a secret. |
| V9 Communications | no | No new network endpoints. |
| V10 Malicious Code | yes | `yaml.safe_load` prevents arbitrary object instantiation (the `yaml.load` CVE class). |
| V11 Business Logic | yes | Fail-closed routing (missing assessment → END, never signal) is the business-critical safety control. |
| V14 Configuration | yes | `risk_policy.yaml` checked into git with defaults; production overrides via a separate file or env-driven path. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| YAML deserialization RCE via `yaml.load` | Elevation of Privilege | Use `yaml.safe_load` ONLY. Enforced in code review; add a ruff rule or grep guard. |
| LLM prompt-injection causes status flip | Tampering | `status` is hard-overwritten in Python AFTER the LLM runs; `Literal["APPROVED","VETOED"]` on the schema means any tampered value raises ValidationError. |
| Stale policy load during pipeline run | Repudiation | `policy_sha` persisted on `RiskAssessment`; structlog event includes SHA; reload-on-each-run documented pitfall; one-time load per pipeline run enforced. |
| SQL injection via PortfolioPosition loader | Tampering | SQLAlchemy ORM; no string concatenation in queries. |
| Correlation / drawdown math blows up on empty / NaN data | DoS | Fail-closed: insufficient-data branches trigger VETO with `constraint_violated="insufficient_price_history"`, not silent zero. |
| Budget DoS on risk_manager_agent | DoS | `get_risk_manager_limits()` with REASONING tier + `output_override=4_000`; pipeline-total cap via existing `PipelineBudgetTracker`. |
| Checkpointer state loss during veto path | Repudiation | `risk_assessment` is in state; LangGraph checkpointer persists state; veto path writes `risk_assessment` before routing — audit trail preserved. |
| Developer mistakenly adds LLM-decided veto path | Safety / Integrity | Unit test `test_status_always_overwritten_from_deterministic_check`; code-review checklist item "no assignments to `status` except the single deterministic-overwrite line". |

## Sources

### Primary (HIGH confidence)

- Context7 `/websites/langchain_oss_python_langgraph` — conditional_edges, `add_conditional_edges` with path_map, Literal return types. Fetched 2026-04-22.
- CLAUDE.md (this repo) — tool-first, immutability, append-only time-series, type hints, ruff, honest positioning.
- `.planning/research/MULTI_AGENT_TRADING_SYSTEMS.md` (existing project research) — canonical source for TradingAgents / FinCon / AlphaAgents / SAS comparisons already adopted by this project.
- `src/ai_hedge_fund/graph/nodes.py::debate_synthesis_node` (existing code) — canonical deterministic-overwrite pattern this phase will mirror.
- `src/ai_hedge_fund/graph/pipeline.py::build_debate_pipeline` (existing code) — canonical topology to extend.
- `src/ai_hedge_fund/db/models.py::DailyPrice + DualTimestampMixin` (existing code) — canonical append-only-SQLAlchemy pattern for `PortfolioPosition`.
- `pyproject.toml` + `uv pip show ...` — version verification for langgraph 1.1.6, pydantic-ai 1.80.0, pyyaml 6.0.3, pandas 3.0.2, numpy 2.4.4, pydantic 2.12.5.

### Secondary (MEDIUM confidence — WebSearch verified with authoritative follow-up)

- [TradingAgents: Multi-Agents LLM Financial Trading Framework (arxiv 2412.20138)](https://arxiv.org/abs/2412.20138) — source for Risk Manager veto pattern, Aggressive/Conservative/Neutral three-debator structure, LangGraph-based implementation.
- [TradingAgents DeepWiki](https://deepwiki.com/TauricResearch/TradingAgents) — reference implementation of the three-debator risk team.
- [FinCon: Synthesized LLM Multi-Agent System with Conceptual Verbal Reinforcement (NeurIPS 2024)](https://proceedings.neurips.cc/paper_files/paper/2024/file/f7ae4fe91d96f50abc2211f09b6a7e49-Paper-Conference.pdf) — CVaR-based within-episode risk control; dual-level risk architecture.
- [AlphaAgents: LLM-Based Multi-Agents for Equity Portfolio Constructions (arxiv 2508.11152)](https://arxiv.org/abs/2508.11152) — risk-tolerance modeling via prompt engineering; debate mechanism for divergent recommendations.
- [BlackRock AlphaAgents write-up (MarkTechPost, Aug 2025)](https://www.marktechpost.com/2025/08/19/blackrock-introduces-alphaagents-advancing-equity-portfolio-construction-with-multi-agent-llm-collaboration/) — multi-agent approach achieves lower drawdowns in risk-averse scenario.

### Tertiary (MEDIUM confidence — standard implementation patterns)

- [Validating YAML Configs Using Pydantic (Better Programming)](https://betterprogramming.pub/validating-yaml-configs-made-easy-with-pydantic-594522612db5) — `yaml.safe_load` + `Model.model_validate` idiom.
- [pyfolio/timeseries.py::max_drawdown (quantopian/pyfolio GitHub)](https://github.com/quantopian/pyfolio/blob/master/pyfolio/timeseries.py) — canonical cumulative-max drawdown implementation.
- [Modelling Drawdown With Python (The Startup, Medium)](https://medium.com/swlh/modelling-drawdown-with-python-98ccb49356ba) — historical-simulation drawdown with pandas.
- [A Comprehensive Review of VaR Methodologies (Spanish Review of Financial Economics)](https://www.elsevier.es/en-revista-the-spanish-review-financial-economics-332-articulo-a-comprehensive-review-value-at-S217312681300017X) — parametric vs historical simulation tradeoffs.
- [LangGraph conditional_edges docs (langchain.com)](https://docs.langchain.com/oss/python/langgraph/graph-api) — path_map pattern, Literal-typed router.
- [pandas.DataFrame.corr docs](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.corr.html) — default Pearson correlation with NaN handling.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — every version verified via `uv pip show`; no new deps.
- Architecture: HIGH — pattern mirrors three existing nodes (`manager_node`, `debate_synthesis_node`, `multi_agent_signal_node`) and an already-documented LangGraph feature (`add_conditional_edges`).
- Portfolio-risk math: HIGH — standard formulas (Pearson corr, cumulative-max drawdown) implemented with battle-tested libs (numpy, pandas); reference implementations in quantopian/pyfolio.
- Policy format: HIGH — `yaml.safe_load` + `pydantic.BaseModel.model_validate` is the well-documented standard.
- Threshold defaults (max_single_position_pct=10, max_sector_pct=30, drawdown=25, corr=0.80): MEDIUM — reasonable industry-standard starting points but user discretion; surfaced as `RiskPolicy` fields for easy tuning. A8 in Assumptions Log.
- Conviction→size mapping: MEDIUM — A4 in Assumptions Log; needs user confirmation or can be deferred to a pure-function swap.
- Test fixtures: HIGH — golden-value tests for correlation and drawdown are computable by hand on a 3-ticker synthetic return series.
- Pitfalls: HIGH — eight identified pitfalls are all rooted in real-world patterns from the cited papers or the existing codebase.

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (30 days — stack is stable, LangGraph conditional_edges API hasn't changed in 1.x)

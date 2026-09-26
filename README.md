# AI Hedge Fund — Multi-Agent Equity Research

**LLM-powered investment research at scale.** Specialist AI analysts research a US stock, a bull and a
bear argue it out in a structured debate, a deterministic risk manager can veto the result, and a
human signs off before anything becomes a signal. Every signal carries a thesis, the evidence behind
it, and a tamper-evident audit trail.

![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-1C3C3C)
![PydanticAI](https://img.shields.io/badge/agents-PydanticAI-E92063)
![PostgreSQL](https://img.shields.io/badge/storage-PostgreSQL%2016-4169E1?logo=postgresql&logoColor=white)
![Claude](https://img.shields.io/badge/LLM-Claude-D97757)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> [!IMPORTANT]
> **Status: research system + paper trading.** No live capital is traded. There is no performance
> track record yet — paper trading infrastructure is complete and the track record starts accruing
> once reviewed signals are submitted to the paper broker. This project does not claim to beat the
> market; see [Honest positioning](#honest-positioning).

---

## Contents

- [How a signal is made](#how-a-signal-is-made)
- [Design principles](#design-principles)
- [Roadmap and status](#roadmap-and-status)
- [Quickstart](#quickstart)
- [Everyday commands](#everyday-commands)
- [Configuration](#configuration)
- [Repository layout](#repository-layout)
- [Development](#development)
- [Research foundations](#research-foundations)
- [Honest positioning](#honest-positioning)
- [License](#license)

---

## How a signal is made

```mermaid
flowchart TD
    T([Ticker + as-of date]) --> M[Research Manager]
    M --> F[Fundamental analyst<br/>SEC filings, XBRL]
    M --> S[Sentiment analyst<br/>news, insider trades]
    M --> Q[Technical analyst<br/>prices, indicators]
    F & S & Q --> SYN[Research synthesis]
    SYN --> D{{5-act bull vs. bear debate}}
    D --> R[Risk Manager<br/>deterministic limits, veto power]
    R -- vetoed --> X([Stopped — never reaches review])
    R -- passed --> H[Human review<br/>approve / reject]
    H --> SIG([Final signal + thesis<br/>stored in episodic memory])
    SIG --> P[Paper execution<br/>deterministic sizing → Alpaca paper]
    P --> MTM[Daily mark-to-market<br/>P&L attributed by analyst, debate side, conviction]
    MTM -.-> G[Promotion gate<br/>Phase 12 — planned]
```

1. **Research.** A Research Manager dispatches three specialist analysts. They work from real data
   — SEC EDGAR filings, Form 4 insider trades, FRED macro series, cached daily prices, and news —
   filtered to what was actually available on the analysis date.
2. **Debate.** A bull advocate and a bear advocate run a fixed five-act protocol: thesis,
   counter-thesis, rebuttal, closing arguments, synthesis. No free-form agent chat.
3. **Risk.** Hard portfolio limits (position size, sector concentration, correlation, projected
   drawdown, exclusions) are enforced in plain Python from [`config/risk_policy.yaml`](config/risk_policy.yaml).
   A veto ends the run.
4. **Human review.** Signals above the review threshold pause the pipeline until a person approves
   or rejects them. This step is non-negotiable.
5. **Paper trading.** Approved signals are sized deterministically and submitted to an Alpaca
   **paper** account. Fills, dividends and daily closes feed an append-only P&L series.

Model routing keeps cost proportional to difficulty: **Claude Haiku** for extraction and
formatting, **Sonnet** for analysis and synthesis, **Opus** for the adversarial debate.

## Design principles

| Principle | What it means in practice |
|---|---|
| **Tool-first numbers** | LLMs never compute ratios, sizes, risk scores or P&L. Deterministic Python does; models write the reasoning. |
| **No look-ahead bias** | Every data point carries an as-of date. Retrieval filters to "known on the analysis date", and SEC data is keyed on filing date, not period end. Regression seeds dated 2099 prove nothing from the future leaks. |
| **Append-only history** | Financial records are never updated in place — enforced by database triggers, not convention. Business date and collection date are stored separately. |
| **Humans are authoritative** | Human review gates every signal; human edits to belief files are never overwritten by the machine. |
| **Audit you can replay** | Each decision records a SHA-256 fingerprint of the exact policy that produced it, so any signal can be reconstructed end to end with `audit_reconstruct`. |
| **Fail closed** | Missing or malformed state stops the pipeline. A vetoed signal is refused before any broker call is made. |
| **Paper only** | The execution layer refuses any non-paper broker host. |

## Roadmap and status

**v1.0 — Multi-agent research system** · shipped 2026-04-23

| Phase | | Status |
|---|---|---|
| 1 | Foundation — LangGraph + PydanticAI, model routing, token budgets, tracing | ✅ |
| 2 | Data ingestion — SEC EDGAR, Form 4, FRED, prices, news, with temporal filtering | ✅ |
| 3 | Single-agent research loop | ✅ |
| 4 | Manager + three specialist analysts | ✅ |
| 5 | Five-act adversarial debate | ✅ |
| 6 | Risk Manager with veto power | ✅ |
| 7 | Episodic + human-readable belief memory, self-critique from outcomes | ✅ |
| 8 | Human review gate, final signal schema, audit trail | ✅ |

**v1.1 — Paper trading + promotion gate** · in progress

| Phase | | Status |
|---|---|---|
| 9 | Append-only paper-trading data layer | ✅ |
| 10 | Paper execution surface — sizing, idempotent submit, veto circuit breaker | ✅ |
| 11 | Daily mark-to-market and P&L attribution | ✅ |
| 12 | Promotion gate — policy-pinned verdict on what has earned live consideration | 📝 planned |
| 13 | Track-record reporting — shareable markdown + verifiable JSON | ⏳ |

Details: [ROADMAP](.planning/ROADMAP.md) · [Milestones](.planning/MILESTONES.md) ·
[Progress log](docs/PROGRESS.md) · [Paper-trading plan](docs/V1.1_PAPER_TRADING_PLAN.md)

## Quickstart

**Prerequisites:** Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```bash
git clone https://github.com/Maxy-Zou/AI-Hedge-Fund.git
cd AI-Hedge-Fund
uv sync --frozen --extra dev          # exact, locked dependency set
docker compose up -d                  # PostgreSQL 16 on localhost:5432
cp .env.example .env                  # then fill in keys — see Configuration
uv run alembic upgrade head           # create the schema
```

Run the full pipeline on one ticker:

```bash
uv run python -m ai_hedge_fund.scripts.run_analysis --ticker AAPL --as-of 2026-09-25
```

If the signal needs review, the run pauses and asks you to approve or reject it in the terminal.

## Everyday commands

All commands are `uv run python -m ai_hedge_fund.scripts.<name>`; add `--help` for options.

| Command | What it does |
|---|---|
| `run_analysis --ticker T --as-of D` | Research → debate → risk → review for one ticker |
| `portfolio_view --as-of D` | Ranked view of current signals, grouped by sector |
| `audit_reconstruct --episodic-id ID` | Rebuild the full decision chain for a signal |
| `submit_signal --episodic-id ID --dry-run` | Show the paper order a reviewed signal would place (drop `--dry-run` to submit) |
| `ingest_fills --since D` | Pull fills, dividends and cash activity from the paper broker |
| `mark_to_market --date D` | Write the day's P&L rows (safe to re-run; never overwrites) |
| `ingest_outcome --ticker T --outcome-pct X --as-of D` | Record a realized outcome and update belief confidence |

## Configuration

Secrets live in `.env` (never committed). Copy [`.env.example`](.env.example) and fill in:

| Variable | Needed for | Get it |
|---|---|---|
| `DATABASE_URL` | Everything | Default works with `docker compose` |
| `ANTHROPIC_API_KEY` | All agent runs | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `EDGAR_IDENTITY` | SEC filings | No signup — `"Your Name you@example.com"` ([SEC policy](https://www.sec.gov/os/accessing-edgar-data)) |
| `FRED_API_KEY` | Macro context | [fredaccount.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys) |
| `FINNHUB_API_KEY` | News, sentiment | [finnhub.io](https://finnhub.io/register) |
| `FMP_API_KEY` | Fundamentals | [financialmodelingprep.com](https://site.financialmodelingprep.com/developer/docs) |
| `ALPACA_PAPER_*` | Paper trading | [alpaca.markets](https://alpaca.markets/) — paper account keys |
| `LANGFUSE_*` | Traces, cost tracking (optional) | [langfuse.com](https://langfuse.com/) — self-host or cloud |

Behaviour is tuned in human-readable YAML under [`config/`](config/): risk limits, review
thresholds, order sizing, and mark-to-market rules. Changing a policy changes its fingerprint, so
every past decision still records which version it ran under.

## Repository layout

```
src/ai_hedge_fund/
├── agents/         Analysts, bull/bear advocates, synthesis, risk manager
├── graph/          LangGraph pipeline, nodes, checkpointing
├── data/           Data clients and tools with temporal filtering
├── risk/           Deterministic portfolio limits
├── review/         Human review gate
├── memory/         Episodic memory, belief files, self-critique
├── output/         Final signal schema, portfolio view
├── schemas/        Typed agent input/output models
├── execution/      Paper sizing and Alpaca paper broker adapter
├── paper/          Append-only paper-trade records
├── mtm/            Daily mark-to-market and P&L attribution
├── observability/  Langfuse tracing, token budgets
└── scripts/        Command-line entry points
alembic/            Database migrations
config/             Human-editable policies (YAML)
tests/              pytest suite
.planning/          Roadmap, requirements, per-phase plans and summaries
```

## Development

```bash
# Full test suite, including the Postgres-only tests
TEST_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund_test \
  uv run pytest -q -rs

# Lint and format
uv run ruff format --check . && uv run ruff check .
```

- About 1,900 tests, running in under a minute. The default suite makes **no real LLM or broker
  calls**; live integration tests run only when the matching API keys are set.
- `uv.lock` is committed and every dependency has an upper bound. Upgrade one package at a time
  with `uv sync --upgrade-package <name>`.
- Work ships phase by phase on `phase/<NN>-<slug>` branches through plan → split → execute →
  review → ship. See [CLAUDE.md](CLAUDE.md) for conventions.

## Research foundations

The architecture follows patterns that independent work has converged on for LLM trading research:
a manager–analyst hierarchy and structured adversarial debate (FinCon, NeurIPS 2024;
TradingAgents; AlphaAgents from BlackRock). Evaluation is kept deliberately sceptical after
FINSABER (KDD 2026), which found LLM strategies generally fail to beat buy-and-hold under rigorous
testing.

## Honest positioning

This is a research system that produces structured, auditable investment theses. It is **not** an
autonomous trading system and makes no claim of generating alpha. All trade-level decisions require
human review, and only paper trading is supported. Nothing in this repository is investment advice.

## License

[MIT](LICENSE) © 2026 Maxy-Zou

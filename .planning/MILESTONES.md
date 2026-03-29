# Milestones

## v1.0 Shared Backtesting Infrastructure (Shipped: 2026-03-29)

**Phases completed:** 8 phases, 20 plans, 26 tasks

**Key accomplishments:**

- fund-backtest package bootstrapped with SQLAlchemy ORM (UniverseTicker + UniverseSnapshot), Alembic migration 001, and Pydantic settings with FUND_BACKTEST_ env prefix
- Wikipedia S&P 400 seeder, yfinance enricher with integer cents conversion, and UniverseBuilder upsert/deactivate orchestrator — 18 unit tests, 84% coverage
- Typer CLI with `universe refresh --dry-run` and `universe status`, plus 7 integration tests confirming mid-cap filtering, cents storage, GICS sector (DATA-07), deactivation-not-deletion, and append-only snapshots against real PostgreSQL
- Append-only price_bars/price_anomalies schema (migration 002) with Pydantic type contracts, round()-based float-to-cents conversion, and PriceSettings config — 18 unit tests all passing
- Chunked yfinance downloader with tenacity retry (5 attempts, exp backoff) and price validator with ±50% anomaly detection, >3-business-day gap flagging, and coverage threshold — 24 unit tests all passing
- PriceBarRepository with append-only ON CONFLICT DO NOTHING inserts and per-bar anomaly exclusion; PriceBuilder orchestrating full download and incremental update with per-ticker start dates — wires together all pure functions from Plans 01 and 02 into a complete price data pipeline
- Three CLI commands (data download, update, coverage) wiring PriceBuilder/PriceBarRepository to Typer; 9 integration tests against PostgreSQL testcontainer proving idempotency, incremental update, anomaly exclusion, and mocked yfinance end-to-end; fixed insert_bars() and insert_anomalies() rowcount using RETURNING clause
- One-liner:
- One-liner:
- Frozen CostConfig and PortfolioResult type contracts with 8 passing type tests and 11 RED engine test stubs defining PortfolioSimulator behavior via hand-calculated references
- Vectorized PortfolioSimulator with borrow/transaction cost model turning 11 RED TDD stubs GREEN; 97% simulator coverage across 106 unit tests
- quantstats-lumi 1.1.3 installed; MetricsBundle (10-field frozen Pydantic model), MetricsConfig, and full TDD scaffold written with 4 GREEN type tests and 15 RED engine tests across RISK-01 through RISK-04
- MetricsEngine.compute() implemented in metrics/engine.py: all 15 RED tests turned GREEN (19 total), 97.75% coverage on metrics/, with periods=252 enforced throughout and three numerical guard cases added
- One-liner:
- One-liner:
- Demo mode only:
- One-liner:
- One-liner:
- One-liner:
- One-liner:

---

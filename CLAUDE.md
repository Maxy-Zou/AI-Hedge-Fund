# AI Hedge Fund

Multi-strategy quantitative trading project. Each strategy lives in its own subfolder with its own CLAUDE.md for strategy-specific context.

## Project Structure

```
AI Hedgefund/
├── CLAUDE.md                # This file — project-wide conventions
├── shared/                  # Common utilities across strategies (when needed)
├── Al Washing Detector/     # Strategy: AI Washing short signal
└── <future strategies>/     # Each subfolder is a self-contained strategy
```

## Stack

- **Language:** Python 3.11+
- **Package management:** TBD per strategy (uv preferred when possible)

## Conventions

- Each strategy subfolder should have its own CLAUDE.md with thesis, data sources, and run instructions
- All API keys and secrets go in `.env` files (never committed)
- Use immutable data patterns — return new objects, don't mutate in place
- Validate all external data (API responses, scraped content, file inputs) at ingestion boundaries

## Data Handling

- Raw data cached locally to avoid redundant API calls
- All timestamps in UTC
- Financial data should preserve source precision (don't round prematurely)

## Running Strategies

Each strategy should define its own entry point and dependencies. Check the strategy's CLAUDE.md for specifics.

# Phase 5: Monitoring Dashboard - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous mode)

<domain>
## Phase Boundary

Users can observe all monitored markets, live signals, open positions, and running P&L from a single screen. This phase delivers a Streamlit dashboard with 4 panels: market monitor, signal feed, position tracker, and P&L view. All data is read-only from the PostgreSQL database. Auto-refresh every ~10 seconds.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion. Key constraints:

- Streamlit + plotly for the dashboard (consistent with fund stack from backtest project)
- Read-only: dashboard never writes to the database
- Auto-refresh every ~10 seconds (Streamlit's st.rerun or auto-refresh mechanism)
- 4 panels as described in success criteria: markets, signals, positions, P&L
- Dashboard runs as a separate process from the polling daemon
- Query from existing ORM models: Market, MarketSnapshot, Signal, Trade

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Fund's backtest project already has Streamlit + plotly patterns to reference
- All ORM models (Market, MarketSnapshot, Signal, Trade) from Phase 1
- Session factory for DB connections
- AppSettings for database URL

### Integration Points
- Dashboard reads from the same PostgreSQL database the daemon writes to
- New entry point: `streamlit run dashboard.py` or similar
- No dependency on the polling daemon process

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond the 4 success criteria. Keep the dashboard simple and functional — data tables with auto-refresh.

</specifics>

<deferred>
## Deferred Ideas

- Charting/visualization beyond basic tables (v2)
- Real-time WebSocket updates (v2)
- Authentication/access control (v2)

</deferred>

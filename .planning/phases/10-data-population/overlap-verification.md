# POP-04 Ticker Overlap Verification

**Status:** Partially verified (Phase 10). Full verification requires Phase 11 (ai-washer universe scan) to complete.

## Verification Commands

### Count overlap (run after Phase 11):

```bash
docker exec ai_hedge_fund_postgres psql -U hedge -d ai_hedge_fund -c "
SELECT COUNT(*) AS overlap_count
FROM universe_tickers ut
JOIN companies c ON ut.ticker = c.ticker
WHERE ut.is_active = TRUE AND c.is_active = TRUE;
"
```

**Minimum required:** 5 (SignalAdapter.min_coverage=5 threshold)
**Expected range:** 50-150 tickers (mid-cap companies likely in both S&P 400 and SEC EDGAR)

### List overlapping tickers (run after Phase 11):

```bash
docker exec ai_hedge_fund_postgres psql -U hedge -d ai_hedge_fund -c "
SELECT ut.ticker, ut.name AS universe_name, c.name AS washer_name
FROM universe_tickers ut
JOIN companies c ON ut.ticker = c.ticker
WHERE ut.is_active = TRUE AND c.is_active = TRUE
ORDER BY ut.ticker;
"
```

## Phase 10 Status

| Metric | Value | Notes |
|--------|-------|-------|
| active_universe | 274 | Populated by Plan 02 — 274 S&P 400 mid-cap tickers |
| active_companies | 0 | Empty — populated by Phase 11 (ai-washer universe scan) |
| overlap | 0 | Expected — companies table empty until Phase 11 |
| SQL syntax | VERIFIED | Both queries execute without error |

## SQL Verification Results (Phase 10)

Executed on 2026-03-30:

```
SELECT active_universe, active_companies, overlap FROM <combined query>
Result: active_universe=274, active_companies=0, overlap=0
```

Both the COUNT query and the list query execute without error — SQL syntax is confirmed correct.

## Phase 11 Post-Condition

- **Gate:** overlap_count >= 5 must be confirmed before Phase 13 (live backtest) can run
- **When to check:** After `ai-washer universe scan` completes in Phase 11
- **If overlap < 5:** SignalAdapter will raise an error and the backtest cannot produce results
- **Recommended minimum:** 50+ tickers for statistically meaningful backtest results

## Context

- fund_backtest uses Wikipedia S&P 400 as universe source (274 active tickers as of 2026-03-30)
- ai_washer uses SEC EDGAR EFTS as company source (searches for AI-related filings)
- Both filter to mid-cap ($2B-$10B), so significant overlap is expected
- SignalAdapter.min_coverage=5 is the hard minimum — if overlap < 5, backtest cannot run
- The companies table has a UNIQUE constraint on `ticker` — JOIN is safe and efficient

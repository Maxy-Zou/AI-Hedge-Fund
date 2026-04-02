# Phase 4: SEC Scoring and Compute Signal - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Produce two signal scores from Phase 3 data: (1) SEC filing mismatch score (0-100) measuring AI keyword frequency growth vs R&D spending growth, and (2) compute spending gap score (0-100) measuring flat CapEx/cloud spending vs AI narrative growth. Store per-signal sub-scores with evidence in the database. No composite scoring — that's Phase 9.

</domain>

<decisions>
## Implementation Decisions

### Keyword Scoring Methodology
- **D-01:** Section-weighted frequency — count AI/ML keywords per filing section (MD&A, Risk Factors, Business Description) with configurable weights per section. MD&A claims weighted higher than Risk Factor boilerplate.
- **D-02:** Curated tiered lexicon — two tiers: vague buzzwords ("AI-powered", "leveraging AI", "machine learning capabilities") vs substantive terms ("neural network", "model training", "inference latency"). Vague terms score higher for washing detection.
- **D-03:** 3-year rolling window for measuring keyword growth trends. Compare current year keyword frequency to 3 years prior.
- **D-04:** Ratio divergence for filing mismatch — compute AI_keyword_growth_rate / R&D_spend_growth_rate. High ratio = growing AI talk with flat R&D = mismatch.

### Compute Spending Gap
- **D-05:** Claude's discretion — use YoY CapEx growth vs keyword growth comparison. Flag companies where keyword growth significantly exceeds CapEx growth over the same window.

### Scoring Normalization
- **D-06:** Claude's discretion — normalize raw metrics to 0-100 range. Research should determine best approach (percentile, min-max, or z-score based on data distribution).

### Evidence Storage
- **D-07:** Claude's discretion — store sufficient evidence in SignalDetail.evidence JSONB for auditability. Should include at minimum: raw keyword counts by section, XBRL values used, growth rates computed.

### Claude's Discretion
- Compute spending gap detection methodology (YoY growth comparison recommended)
- Scoring normalization approach (percentile vs min-max vs z-score)
- Evidence JSONB schema (must be audit-sufficient)
- Specific keyword lists (vague vs substantive terms)
- Section weight values for keyword counting
- Cloud/compute partnership mention keywords for COMP-02

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Core value, constraints, integration pattern
- `.planning/REQUIREMENTS.md` — SEC-02, SEC-04, COMP-01, COMP-02, COMP-03, SCORE-02 acceptance criteria

### Research
- `.planning/research/STACK.md` — FinBERT for sentiment (Phase 7), not needed here
- `.planning/research/ARCHITECTURE.md` — Component boundaries, scoring engine design
- `.planning/research/PITFALLS.md` — Keyword frequency pitfalls, look-ahead bias

### Phase 3 Artifacts (Data Source)
- `src/ai_washer/db/models.py` — Filing, XBRLFact, DailyScore, SignalDetail models
- `src/ai_washer/ingestion/types.py` — FilingData, FilingSections, XBRLFactRecord, XBRL_TAG_GROUPS
- `src/ai_washer/ingestion/filing_client.py` — FilingClient patterns (reuse for data access)
- `src/ai_washer/ingestion/xbrl_extractor.py` — XBRLExtractor (R&D, CapEx, revenue already extracted)
- `src/ai_washer/config.py` — AppSettings, UniverseSettings, FilingCollectionSettings patterns

### Phase 1-2 Artifacts (Infrastructure)
- `src/ai_washer/db/base.py` — AppendOnlyMixin, DualTimestampMixin
- `config/scoring.yaml` — Signal weights configuration (Jobs 25%, SEC 20%, etc.)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Filing` model — has `sections` JSONB with MD&A, Risk Factors, Business Description text
- `XBRLFact` model — has `concept` (R&D, CapEx, revenue), `value_cents`, `end_date`, `fiscal_period`
- `DailyScore` model — ready for composite scores (Phase 9), partitioned by `scored_at`
- `SignalDetail` model — `signal_type` (String), `sub_score` (Float), `evidence` (JSONB) — target for Phase 4 output
- `config/scoring.yaml` — already has signal weights and threshold ranges

### Established Patterns
- Pydantic types in `types.py` per subpackage for all data contracts
- ORM models extend AppendOnlyMixin for append-only semantics
- Config via Pydantic BaseModel with Field defaults
- structlog for structured logging
- tenacity for retry logic (not needed here — data already local)
- Deterministic pipelines: sort inputs, pin dates (from universe builder)

### Integration Points
- New `src/ai_washer/analysis/` package for scoring engines
- Read from `Filing` and `XBRLFact` tables (Phase 3 output)
- Write to `SignalDetail` table (per-signal sub-scores)
- CLI `score` subcommand group for manual scoring runs

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. The key thesis: companies that talk more about AI while spending less on R&D/compute are washing.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-sec-scoring-and-compute-signal*
*Context gathered: 2026-03-28*

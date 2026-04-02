# Phase 4: SEC Scoring and Compute Signal - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-28
**Phase:** 04-sec-scoring-and-compute-signal
**Areas discussed:** Keyword scoring methodology

---

## Keyword Scoring Methodology

### Q1: How should AI/ML keywords be counted across filing sections?

| Option | Description | Selected |
|--------|-------------|----------|
| Section-weighted frequency (Recommended) | Count keywords per section with configurable weights. MD&A weighted higher than Risk Factor boilerplate. | ✓ |
| Simple total frequency | Count all keywords across entire filing text. Treats boilerplate same as claims. | |
| TF-IDF relative to corpus | Weight by inverse document frequency. More sophisticated but harder to explain. | |

**User's choice:** Section-weighted frequency (Recommended)

### Q2: How should the filing mismatch score combine keyword growth with R&D spending growth?

| Option | Description | Selected |
|--------|-------------|----------|
| Ratio divergence (Recommended) | AI_keyword_growth_rate / R&D_spend_growth_rate. High ratio = mismatch. | ✓ |
| Percentile rank difference | Rank keyword and R&D growth as percentiles, score the gap. | |
| You decide | Claude picks during planning. | |

**User's choice:** Ratio divergence (Recommended)

### Q3: What keyword list approach for detecting AI claims?

| Option | Description | Selected |
|--------|-------------|----------|
| Curated tiered lexicon (Recommended) | Two tiers: vague buzzwords vs substantive terms. Vague terms score higher for washing. | ✓ |
| Flat keyword list | Single list, all weighted equally. Can't distinguish buzzwords from substance. | |
| You decide | Claude designs lexicon during research. | |

**User's choice:** Curated tiered lexicon (Recommended)

### Q4: What time window for measuring keyword growth trends?

| Option | Description | Selected |
|--------|-------------|----------|
| 3-year rolling window (Recommended) | Compare current year to 3 years prior. Matches corporate strategy cycles. | ✓ |
| 5-year rolling window | Longer view but may include pre-AI-hype baseline. | |
| You decide | Claude picks based on data availability. | |

**User's choice:** 3-year rolling window (Recommended)

---

## Claude's Discretion

- Compute spending gap detection methodology
- Scoring normalization approach (0-100)
- Evidence JSONB schema
- Specific keyword lists (vague vs substantive terms)
- Section weight values
- Cloud/compute partnership keywords

## Deferred Ideas

None — discussion stayed within phase scope.

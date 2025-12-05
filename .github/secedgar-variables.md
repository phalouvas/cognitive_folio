# Cognitive Folio – SEC Edgar Variable Plan (cache-only)

## Executive Summary
- Goal: add secedgar-backed statement variables with automatic Yahoo Finance fallback, using `{{financials:y<years>:q<quarters>}}` for parameterized financial data expansion; no CF Financial Period DocType is present.
- Rule: use cached secedgar data if it already exists on `CF Security`; never trigger on-demand Edgar fetch during prompt expansion. If secedgar cache is absent or unreadable, fall back to cached yfinance JSON. Prompts must never fail.

## Architecture (target)
```
CF Security
  - yfinance JSON cached (income/balance/cashflow/dividends...) in existing fields (keep as-is)
  - secedgar data served from edgartools' caching engine on disk (do not persist to DB)
→ prompt variable replacement (cache-only; secedgar preferred)
→ AI prompts
```

## Variable Syntax & Decision Rule
- Parameterized: `{{financials:y<years>:q<quarters>}}` expands financial statements as markdown with specified periods. Examples:
  - `{{financials:y5:q10}}` → 5-year annual + 10 quarters
  - `{{financials:y3:q0}}` → 3 years annual only
  - `{{financials:y10:q16}}` → 10 years + 16 quarters (full depth)
- For each statement, prefer secedgar (cached on disk via edgartools cache); if missing, fall back to cached yfinance JSON fields; if nothing, emit a short placeholder.
- Market data passthrough (existing): `{{ticker_info.field}}` stays unchanged.
- Decision: edgar cache on disk first; yfinance cache second; never fetch edgar at prompt time; never fail the prompt.

## Remaining Implementation (what's left to do)

### A) Resolver + fallback wiring (still needed)
- Add `get_cached_yfinance_data(security)` to parse existing yfinance JSON fields on `CF Security` (fallback path).
- Add `expand_financials_variable(security, annual_years, quarterly_count)` to emit concatenated markdown for all statements with specified periods, preferring edgar cache (via existing `get_edgar_data`) and falling back to yfinance; placeholder if none.
- Extend variable resolver to match `{{financials:y(\d+):q(\d+)}}` and replace using the handler; preserve existing `{{ticker_info.*}}` and doc-field replacements.

### B) Wire into prompt generation
- In `cognitive_folio/cognitive_folio/doctype/cf_chat_message/cf_chat_message.py` (`prepare_prompt`), run the new resolver after existing portfolio/holdings substitutions so `{{financials:y<years>:q<quarters>}}` expands using cache-only data (edgar-first, then yfinance).
- Apply the same resolver for portfolio-level prompts if those templates include these variables.

### C) Update prompt templates
- `.github/prompt_1.md` / `_2` / `_3`: replace prior period placeholders with `{{financials:y<years>:q<quarters>}}`; note: "Use cached secedgar if present; otherwise use cached Yahoo Finance; do not fetch during prompt expansion."

### D) Tests
- Unit tests (mocked): edgar present with y5:q10 → edgar tables rendered with 5 years + 10 quarters; edgar absent → yfinance fallback; both absent → placeholder string; malformed JSON handled gracefully; invalid period params handled gracefully.
- Integration smoke: `prepare_prompt` with mixed variables including `{{financials:y3:q8}}` ensures substitutions complete without raising.

### E) Dependencies & ops
- Ensure `pandas` and `yfinance` remain listed; edgar caching (already via `get_edgar_data` in `CF Security.fetch_data`) relies on prior ingestion. Do **not** call edgar in the resolver path; use cache-only access.

## Regex shapes (parameterized notation)
- Financials with periods: `\{\{financials:y(\d+):q(\d+)\}\}`
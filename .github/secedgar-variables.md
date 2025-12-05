# Cognitive Folio – SEC Edgar Variable Plan (cache-only)

## Executive Summary
- Goal: add secedgar-backed statement variables with automatic Yahoo Finance fallback, plus `{{compare}}` for multi-table expansion; no CF Financial Period DocType is present.
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
- Edgar (cached): `{{edgar.balance_sheet}}`, `{{edgar.income_statement}}`, `{{edgar.cash_flow}}`, `{{edgar.equity}}`
- YFinance (fallback): `{{yfinance.balance_sheet}}`, `{{yfinance.profit_loss}}`, `{{yfinance.cash_flow}}`
- Composite: `{{compare}}` → expand all available statements; prefer secedgar tables, else yfinance tables.
- Market data passthrough (existing): `{{ticker_info.field}}`
- Decision: if cached secedgar exists → use it; else use cached yfinance. If neither exists, return a short placeholder note and continue.

## Implementation Steps

### 1) Handlers in `cognitive_folio/utils/helper.py`
- Add cache readers:
  - `get_cached_secedgar_data(security)` → parse stored secedgar JSON field; return dict or None.
  - `get_cached_yfinance_data(security)` → parse existing yfinance JSON fields; return dict or None.
- Add resolvers (cache-only):
  - `handle_edgar_variable(security, var_name)` → lookup in cached secedgar data by dot path; render dict/list via pandas `to_markdown`; return None on miss.
  - `handle_yfinance_variable(security, var_name)` → lookup in cached yfinance data; render via pandas `to_markdown`; return None on miss.
  - `expand_compare_variable(security)` → emit concatenated markdown tables: prefer secedgar keys (`balance_sheet`, `income_statement`, `cash_flow`, `equity` if present); else yfinance (`balance_sheet`, `profit_loss`, `cash_flow`). If nothing, return a placeholder string.
- Extend variable resolver (without fetching):
  - Match `{{compare}}`, `{{edgar.<path>}}`, `{{yfinance.<path>}}` and replace using the handlers.
  - Preserve existing `{{ticker_info.*}}` and doc-field replacements.

  ### 1b) Cache secedgar during fetch
  - In `CF Security.fetch_data` (or a sibling background job), when `with_fundamentals=True` and CIK is known, call edgartools using its built-in caching engine to pull filings/XBRL once; rely on that filesystem cache and do **not** persist secedgar payloads to DB.
  - Preserve the existing yfinance fetch/storage path unchanged; edgar caching is additive and uses the cache engine, not live fetch during prompt expansion.
  - Do not call edgar in prompt-time resolvers; all edgar access must happen here (or another fetch job) so prompt expansion stays cache-only.

### 2) Wire into prompt generation
- In `cognitive_folio/cognitive_folio/doctype/cf_chat_message/cf_chat_message.py` (`prepare_prompt`), run the new resolver after existing portfolio/holdings substitutions so `{{compare}}`, `{{edgar.*}}`, and `{{yfinance.*}}` expand using cache-only data.
- Apply the same resolver for portfolio-level prompts if those templates include these variables.

### 3) Update prompt templates
- `.github/prompt_1.md` / `_2` / `_3`: replace prior period placeholders with `{{compare}}` or explicit `{{edgar.balance_sheet}}` / `{{edgar.income_statement}}` etc., and note: “Use cached secedgar if present; otherwise use cached Yahoo Finance; do not fetch during prompt expansion.”

### 4) Tests
- Unit tests (mocked): secedgar present → edgar tables rendered; secedgar absent → yfinance fallback; both absent → placeholder string; malformed JSON handled gracefully.
- Integration smoke: `prepare_prompt` with mixed variables ensures substitutions complete without raising.

### 5) Dependencies & ops
- Ensure `pandas` and `yfinance` remain listed; secedgar caching relies on prior ingestion (no runtime fetch here). If edgartools is used elsewhere to populate cache, keep it pinned, but **do not** call it in the resolver path.

## Regex shapes (dot notation)
- Edgar: `\{\{edgar\.([\w_\.]+)\}\}`
- YFinance: `\{\{yfinance\.([\w_\.]+)\}\}`
- Compare: `\{\{compare\}\}`
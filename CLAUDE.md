# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development
```bash
# Install app (from bench root)
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app cognitive_folio

# Setup pre-commit hooks
cd apps/cognitive_folio
pre-commit install

# Run migrations
bench --site tmp.localhost migrate

# Start development server
bench start

# Run background job worker (separate terminal)
bench worker --queue long

# Check pending jobs
bench show-pending-jobs
```

### Testing
```bash
# Run all tests for the app
bench --site tmp.localhost run-tests --app cognitive_folio

# Execute specific function (debugging)
bench --site tmp.localhost execute cognitive_folio.tasks.auto_fetch_portfolio_prices
```

### Linting & Formatting
- **Pre-commit hooks** run automatically on commit (ruff, eslint, prettier, pyupgrade).
- **Ruff** configuration in `pyproject.toml` (line length 110, tab indent).
- **ESLint** and **Prettier** for JavaScript.
- Manually run `ruff check --fix` and `ruff format` if needed.

## Architecture

### Overview
Cognitive Folio is a **Frappe/Bench app** (version 16) for AI‑optimized portfolio management. It fetches security prices/news, generates AI suggestions via OpenAI/OpenWebUI, and maintains conversation audit trails.

### Core DocTypes
- **CF Security**: Stock/cash holdings with price/news fetch, AI suggestions, fair value targets, CIK lookup.
- **CF Portfolio**: Aggregates holdings, runs portfolio‑level AI analysis, batch news evaluation & suggestion generation.
- **CF Portfolio Holding**: Per‑holding metrics (allocation %, dividends, currency conversion, AI suggestions).
- **CF Chat / CF Chat Message**: AI conversation audit trail with background processing (states: Processing → Success/Failed), real‑time status updates.
- **CF Settings**: OpenAI/OpenWebUI endpoint config, model list management, URL‑fetch limits, system prompt templates.

### AI Generation Flow
- **Security‑level AI**: `CF Security.process_security_ai_suggestion` queues to background `long` queue → parses JSON response → creates `CF Chat` + `CF Chat Message` for audit → emits `cf_job_completed` real‑time event.
- **Portfolio‑level AI**: `CF Portfolio.process_portfolio_ai_analysis` → saves HTML suggestion → logs chat → notifies real‑time; also `evaluate_holdings_news()` for batch news eval.
- **Chat Messages**: Enqueued via `.process()` method (async) → status: Processing → Success/Failed → real‑time notification. No true streaming; uses background job queue with token budget ~60k via tiktoken. Previous messages replayed newest‑first until budget exhausted.
- All background jobs run on `long` queue with 30‑min timeout; errors logged & user notified via real‑time `cf_job_completed` event.

### Scheduled Tasks
- **Price fetch**: Daily 3 AM via `auto_fetch_portfolio_prices` (stocks only, portfolio must have `auth_fetch_prices=1`).
- **News evaluation**: Daily 4 AM via `auto_evaluate_holdings_news` (separate scheduled job; also callable as `CF Portfolio.evaluate_holdings_news()`).

### Data & Conversions
- **Currency**: GBP rates divided by 100 (yfinance returns GBP/100).
- **Dividends**: Sum from security history JSON, filtered by portfolio start date, converted to portfolio currency.
- **Price/P&L**: Use `base_average_purchase_price` for calculations; cash securities locked at `current_price=1.0`.

### Prompt Templating
- **Portfolio prompts**: `((field))` → `CF Portfolio` field. `***HOLDINGS*** ... ***HOLDINGS***` expands per holding with `{{field}}` (CF Security) and `[[field]]` (CF Portfolio Holding).
- **Security prompts**: `{{field}}` supports nested JSON paths & wildcard `ARRAY` handling (see `utils.helper.replace_variables`).
- **Financial variables**: `{{financials:y<years>:q<quarters>}}` → JSON statements (tries SEC Edgar first, falls back to yfinance cached fields).
- **Edgar qualitative text**: `{{edgar:form_type:year_or_index[:section][:quarter]}}` (form types: `10‑K`, `10‑Q`, `8‑K`; sections: `risk`, `mda`, `business`, `legal`, `all`).

### URL Embedding & PDF References
- **URL embedding**: Via `utils.url_fetcher.fetch_and_embed_url_content`. Limits controlled by `CF Settings` (`max_url_fetch`, `url_fetch_timeout`, byte/character caps).
- **PDF references**: `<<file.pdf>>` in chat prompts → inlined with tables via `pdfplumber`.
- **Web search**: Optional `web_search` flag in chat messages → builds query, prepends results to prompt.

## Development Notes
- **Dependencies**: `yfinance`, `openai`, `edgartools` installed via `install.after_install`.
- **Background jobs**: Use Redis queue `long`; run workers separately for testing.
- **Testing**: No built‑in test harness; use bench `execute` to exercise functions. Temp helpers can be added to `cognitive_folio/utils/tmp_testing.py` and removed after use.
- **When modifying AI flows**: Preserve real‑time notifications (`cf_job_completed`, `cf_streaming_update`), always create `CF Chat` + `CF Chat Message` records for auditability, respect `long` queue timeout (30 min), maintain token budget logic (~60k), handle errors gracefully (log via `frappe.log_error`, notify user via real‑time, save partial results when possible).
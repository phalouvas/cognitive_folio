# Copilot Instructions for `cognitive_folio`

## Quick Reference

**What**: AI-assisted portfolio management app for Frappe/ERPNext. Fetches security prices/news, generates AI suggestions via OpenAI/OpenWebUI, and stores conversations.

**Core DocTypes**:
- `CF Security`: Stock/cash holdings with price/news fetch, AI suggestions, fair value targets, CIK lookup
- `CF Portfolio`: Aggregates holdings, runs portfolio-level AI analysis, batch news evaluation & suggestion generation
- `CF Portfolio Holding`: Per-holding metrics (allocation %, dividends, currency conversion, AI suggestions)
- `CF Chat` / `CF Chat Message`: AI conversation audit trail with background processing (states: Processing → Success/Failed), realtime status updates
- `CF Settings`: OpenAI/OpenWebUI endpoint config, model list management, URL-fetch limits, system prompt templates

**Supporting DocTypes**:
- `CF Prompt`: Prompt templates with variable validation & system content
- `CF AI Model`: Available models from OpenWebUI/OpenAI with metadata
- `CF Dividend`: Dividend income tracking per security with date & amount
- `CF Transaction`: Transaction history audit trail (optional)
- `CF Asset Allocation`: Portfolio allocation targets & tracking

**Key Features**:
- **Price fetch**: Daily 3 AM via `auto_fetch_portfolio_prices` (stocks only, portfolio must have `auth_fetch_prices=1`)
- **News eval**: Daily 4 AM via `auto_evaluate_holdings_news` (separate scheduled job; also callable as `CF Portfolio.evaluate_holdings_news()`)
- **Batch operations**: `CF Portfolio.fetch_holdings_data(with_fundamentals)` (with progress), `generate_holdings_ai_suggestions()` (queues AI for each holding)
- **Chat export**: Via `CF Chat.export_chat_to_json()` or amend existing with `amend_cf_chat()` 
- **Workspace sidebar**: Custom nav widget in `workspace_sidebar/cognitive_folio.json`
- **List actions**: Batch fetch/AI suggestion buttons in CF Security & CF Portfolio Holding list views

**Common Commands**:
```bash
bench --site tmp.localhost migrate
bench --site tmp.localhost execute cognitive_folio.tasks.auto_fetch_portfolio_prices
bench --site tmp.localhost run-tests --app cognitive_folio
bench worker --queue long  # Run background jobs
bench show-pending-jobs    # Debug stuck jobs
```

---

## Core Architecture

### AI Generation Flow
- `CF Security`: `process_security_ai_suggestion` queues to background `long` queue → parses JSON response → creates `CF Chat` + `CF Chat Message` for audit → emits `cf_job_completed` realtime event
- `CF Portfolio`: `process_portfolio_ai_analysis` → saves HTML suggestion → logs chat → notifies realtime; also `evaluate_holdings_news()` for batch news eval
- `CF Chat Message`: Enqueued via `.process()` method (async) → status: Processing → Success/Failed → realtime notification. **Note**: No true streaming; uses background job queue with token budget ~60k via tiktoken. Previous messages replayed newest-first until budget exhausted.
- All background jobs run on `long` queue with 30-min timeout; errors logged & user notified via realtime `cf_job_completed` event

### Data & Conversions
- **Currency**: GBP rates divided by 100 (yfinance returns GBP/100)
- **Dividends**: Sum from security history JSON, filtered by portfolio start date, converted to portfolio currency
- **Price/P&L**: Use `base_average_purchase_price` for calculations; cash securities locked at `current_price=1.0`

### CF Settings & Configuration
- `open_ai_url`: Base URL for OpenAI or OpenWebUI API endpoint
- `open_ai_api_key`: Secret key (stored encrypted)
- `check_openwebui_connection()`: Tests connection, auto-populates `ai_models` child table with available models
- `default_ai_model`: Default model for new chats (selected from `ai_models` after connection test)
- URL-fetch limits: `max_url_fetch`, `url_fetch_timeout`, byte/char caps for embeddings

### CF Chat Operations
- **Create**: via `CF Chat` DocType with optional context (security/portfolio/custom prompt)
- **Amend**: Use `amend_cf_chat(chat_name)` → creates new chat with `duplicated_from` reference, copies messages
- **Export**: `export_chat_to_json(chat_name)` → JSON with timestamps, prompts, responses for archival

---

## Supporting Features

### CF Prompt Management
- Store & reuse prompt templates with variable placeholders
- `validate_prompt()`: Validates syntax of variables in prompt text
- `test_prompt(context)`: Test prompt expansion without running AI
- System prompts stored in `CF Settings` for default behavior

### CF Dividend Tracking
- Record dividend income per security
- `fetch_shares_owned()`: Auto-populate shares at dividend date from portfolio holdings
- Filtered in portfolio analysis: only sum dividends after portfolio start date

### CF AI Model Registry
- Auto-populated from `CF Settings.check_openwebui_connection()`
- Stores model_id, object_type, owned_by from OpenAI/OpenWebUI API
- Used for dropdown in chat/suggestion forms

---

## Advanced Topics

### Prompt Templating

**Portfolio prompts**: 
- `((field))` → `CF Portfolio` field
- `***HOLDINGS*** ... ***HOLDINGS***` → expands per holding with:
  - `{{field}}` → `CF Security` field (supports nested JSON, wildcards)
  - `[[field]]` → `CF Portfolio Holding` field

**Security prompts**: `{{field}}` supports nested JSON paths & wildcard `ARRAY` handling (see `utils.helper.replace_variables`)

**Financial variables**: 
- `{{financials:y<years>:q<quarters>}}` → JSON statements (e.g., `{{financials:y10:q16}}`)
  - Tries SEC Edgar first (US stocks with CIK via `get_edgar_data`)
  - Falls back to yfinance cached fields: `profit_loss`, `balance_sheet`, `cash_flow`

**Edgar qualitative text variables**: `{{edgar:form_type:year_or_index[:section][:quarter]}}`
- Form types: `10-K` (annual), `10-Q` (quarterly), `8-K` (material events)
- Sections: `risk`, `mda`, `business`, `legal`, `all` (default: risk+mda+business)
- Year/index: `-1` (latest), `-2` (previous), or absolute year (2024)
- 8-K special: `-3` gets latest 3 filings; year aggregates all from that year
- Limit: 200K chars + metadata. Examples: `{{edgar:10-K:-1:risk}}`, `{{edgar:10-Q:-1::Q2}}`, `{{edgar:8-K:-3}}`
- Integrated via `get_edgar_section()` & `expand_edgar_section_variable()` in `helper.py`

### Data Ingestion

**URL embedding** (chat prompts): Via `utils.url_fetcher.fetch_and_embed_url_content`
- Limits: `CF Settings` controls `max_url_fetch`, `url_fetch_timeout`, byte/character caps
- HTML → markdown via `markdownify` with fallback
- Max PDF size: 50MB

**PDF references**: `<<file.pdf>>` in chat prompts → inlined with tables via `pdfplumber`

**Web search**: Optional `web_search` flag in chat messages → builds query, prepends results to prompt

### Financial Data Coverage

Use `CF Security.get_financial_data_coverage()` to check available data from yfinance & SEC Edgar (annual years, quarterly periods).

---

## Development

### Setup & Workflow
- Bench app; typical site: `tmp.localhost`
- Dependencies: `yfinance`, `openai`, `edgartools` (installed via `install.after_install`)
- Code style: ruff (line length 110, tab indent), eslint, prettier, pyupgrade; configs in `pyproject.toml`
- Background jobs use Redis queue `long`; run workers separately for testing

### Testing & Debugging
- No built-in test harness; use bench to exercise: `bench --site tmp.localhost execute cognitive_folio.utils.markdown.safe_markdown_to_html --args '["**bold**"]'`
- Temp helpers: add to `cognitive_folio/utils/tmp_testing.py`, remove after use
- Stuck jobs: Check `frappe.log_error` logs, run `bench show-pending-jobs`, verify Redis queue

### When Modifying AI Flows
- Preserve realtime notifications (`cf_job_completed`, `cf_streaming_update`)
- Always create `CF Chat` + `CF Chat Message` records for auditability
- Respect `long` queue timeout (30 min) for long-running operations
- Maintain token budget logic (~60k) when adding context sources
- Handle errors gracefully: log via `frappe.log_error`, notify user via realtime, save partial results when possible

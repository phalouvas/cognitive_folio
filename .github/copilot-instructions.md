# Cognitive Folio - AI Coding Agent Guide

**Cognitive Folio** is a Frappe-based investment portfolio management application with AI-driven financial analysis. Built on the Frappe Framework (ERPNext ecosystem), it provides structured financial data management and AI-powered investment insights.

## Architecture Overview

### Core Framework: Frappe
This is a **Frappe App** - not a standalone application. Key implications:
- Uses Frappe's ORM: `frappe.get_doc()`, `frappe.get_all()`, `frappe.db.get_value()`
- DocTypes are the data models (not traditional Django/SQLAlchemy models)
- Server-side: Python methods use `@frappe.whitelist()` decorator for client access
- Client-side: JavaScript controllers in `{doctype}.js` files use `frappe.ui.form.on()`
- Install via bench: `bench get-app` → `bench install-app cognitive_folio`

### Key DocTypes (Data Models)
**Primary entities** (in `cognitive_folio/cognitive_folio/doctype/`):
- `CF Security` - Individual stocks/securities with real-time pricing (yfinance) and AI analysis
- `CF Financial Period` - Structured financial statements (income, balance sheet, cash flow) with auto-calculated metrics
- `CF Portfolio` - Investment portfolios with holdings aggregation and AI-driven rebalancing
- `CF Portfolio Holding` - Individual positions within portfolios (with real-time P&L tracking)
- `CF Chat` / `CF Chat Message` - AI conversation threads linked to securities/portfolios
- `CF Transaction` - Buy/sell/dividend records
- `CF AI Model` - Configurable AI model settings (OpenAI, Claude, etc.)

### Data Flow Architecture
1. **Financial Data Pipeline** (US stocks prioritize SEC Edgar over Yahoo Finance):
   - User triggers "Fetch Fundamentals" action on CF Security
   - System checks if US stock → tries SEC Edgar (XBRL parsing, quality score 95)
   - Falls back to Yahoo Finance (quality score 85) for non-US or failures
   - Creates/updates CF Financial Period records with structured data
   - Auto-calculates margins (gross/operating/net), ratios (ROE, ROA, D/E), and YoY growth
   - Data quality scores determine override logic (higher quality sources take precedence)

2. **AI Integration Pattern**:
   - User selects AI model from CF AI Model (stores API keys, model names)
   - Prompts use template variable replacement: `{{field_name}}` for doc fields, `{{field.nested.path}}` for JSON
   - Financial data injected via special tags: `{{periods:annual:5}}` for last 5 annual periods
   - AI responses stored in markdown fields, converted to HTML via `safe_markdown_to_html()`
   - Streaming responses handled client-side with EventSource for real-time display

## Development Conventions

### Python Backend Patterns

**DocType Lifecycle Hooks** (in order of execution):
```python
def validate(self):              # Pre-save validation + auto-calculations
def before_save(self):           # Rarely used (prefer validate)
def after_insert(self):          # Post-creation tasks (e.g., fetch initial data)
def on_update(self):             # Post-save tasks (e.g., trigger child updates)
def on_trash(self):              # Cleanup related records on deletion
```

**Common Patterns**:
- Auto-calculation in `validate()`: `CF Financial Period` computes margins/ratios before save
- Cascade updates in `on_update()`: `CF Security` triggers all linked `CF Portfolio Holding` saves
- Lazy loading expensive data: `fetch_data()` methods called only when needed, not on every save
- Quality score conflict resolution: Check `data_quality_score` before overwriting existing data

**Whitelisted API Methods**:
```python
@frappe.whitelist()
def import_from_yahoo_finance(security_name, replace_existing=False, respect_override=True):
    """Client-callable via frm.call() or frappe.call()"""
```

### JavaScript Client-Side Patterns

**Form Controllers** (`{doctype}.js`):
```javascript
frappe.ui.form.on('CF Security', {
    refresh: function(frm) {
        // Add custom buttons, format displays
        frm.add_custom_button(__('Fetch Latest Data'), () => {
            frm.call({
                doc: frm.doc,
                method: 'fetch_data',  // Python method on Document class
                args: { with_fundamentals: false },
                callback: (r) => { frm.reload_doc(); }
            });
        });
    },
    validate: function(frm) {
        // Client-side validation before save
    }
});
```

**Display Formatting**:
- Financial JSON data rendered via custom HTML: `frm.set_df_property('field_html', 'options', html_string)`
- Markdown previews: `frappe.markdown(text)` converts to HTML client-side
- Custom indicators: `frm.dashboard.add_indicator()` for status badges

### Financial Data Quality System

**Source Priority** (higher score = authoritative):
1. Manual Entry (100) - User-verified data, never auto-overwritten
2. PDF Upload (95) - Extracted from official reports
3. SEC Edgar (95) - US regulatory filings (10-K, 10-Q) with XBRL parsing
4. Yahoo Finance (85) - Third-party aggregator (global coverage)

**Conflict Resolution**:
- Check `override_yahoo` flag: If True, skip Yahoo Finance updates entirely
- Compare `data_quality_score`: Only update if new source >= existing source
- SEC Edgar auto-upgrades Yahoo Finance data for US companies

### SEC Edgar Integration (US Stocks Only)

**Implementation** (`utils/sec_edgar_fetcher.py`):
- Uses `sec-edgar-downloader` to fetch 10-K/10-Q filings as HTML
- Parses inline XBRL with `python-xbrl` library (extracts US-GAAP facts)
- Maps XBRL tags → CF Financial Period fields (e.g., `us-gaap:Revenues` → `total_revenue`)
- Handles multiple contextualized values (consolidated, segments, historical comparisons)
- Creates quarterly/annual CF Financial Period records with quality score 95

**Required Libraries** (install in bench env):
```bash
./env/bin/pip install yfinance openai sec-edgar-downloader python-xbrl lxml pdfplumber
```

### Helper Utilities

**Template Variable Replacement** (`utils/helper.py`):
- `replace_variables(match, doc)`: Expands `{{field_name}}` or `{{json_field.nested.key}}`
- Supports array wildcards: `{{news.ARRAY.title}}` → comma-separated list
- Used in AI prompts and report templates

**Markdown Safety** (`utils/markdown.py`):
- `safe_markdown_to_html(text)`: Sanitizes markdown before HTML conversion (prevents XSS)
- Validates table structures, cleans dangerous HTML tags

## Critical Workflows

### Adding a New Security
1. Create CF Security with symbol (e.g., "AAPL")
2. `after_insert()` auto-triggers `fetch_data(with_fundamentals=True)`:
   - Fetches current price via yfinance
   - For US stocks: Downloads SEC Edgar filings → creates CF Financial Periods
   - For others: Falls back to Yahoo Finance financials
3. `generate_ai_suggestion()` creates initial AI analysis using configured model

### Updating Financial Data
User action: `Actions → Fetch Fundamentals` (or via scheduled jobs):
1. `cf_security.py`: `fetch_fundamentals()` determines US vs non-US
2. US: `sec_edgar_fetcher.fetch_sec_edgar_financials(security_name, cik)`
   - Downloads last 3 years of 10-K + 12 quarters of 10-Q
   - Parses XBRL → upserts CF Financial Period records
3. Non-US: `import_from_yahoo_finance(security_name)`
   - Fetches quarterly/annual data from yfinance
   - Creates CF Financial Period records (quality score 85)
4. `CF Financial Period.validate()` auto-calculates missing fields (e.g., gross_profit = revenue - COGS)

### Portfolio Rebalancing
1. User modifies target allocations in CF Asset Allocation (child table of CF Portfolio)
2. `cf_portfolio.py`: `calculate_rebalancing()` compares current vs target percentages
3. Generates buy/sell recommendations (stored in `rebalancing_actions` markdown field)
4. User reviews suggestions → manually creates CF Transaction records to execute trades

## Testing & Debugging

**Run Python Tests**:
```bash
cd frappe-bench
bench run-tests --app cognitive_folio --doctype "CF Financial Period"
```

**Frappe Console** (for quick queries):
```bash
bench console
>>> doc = frappe.get_doc("CF Security", "AAPL")
>>> doc.fetch_fundamentals()
```

**Common Debug Points**:
- Check logs: `frappe-bench/logs/` (errors automatically logged via `frappe.log_error()`)
- Test XBRL parsing: Run `sec_edgar_fetcher.py` functions directly in console
- Verify data quality: Check `CF Financial Period.data_quality_score` and `override_yahoo` flag

## Project-Specific Gotchas

1. **Frappe ORM Quirks**:
   - `frappe.get_doc()` loads the full document; use `frappe.db.get_value()` for single fields
   - Child table updates require parent save: `parent_doc.save()` propagates to children
   - Avoid `doc.save()` inside loops (use `bulk_insert` for batch operations)

2. **SEC Edgar Limitations**:
   - Only works for US-listed companies with CIK (Central Index Key)
   - XBRL mapping is best-effort (some custom tags may not map cleanly)
   - Rate limits: SEC requests require `User-Agent` header (set in downloader)

3. **AI Model Configuration**:
   - API keys stored in CF AI Model DocType (not environment variables)
   - System prompt assembled from: model's system_prompt + doc fields via `{{variables}}`
   - Streaming responses require client-side EventSource handling (see `cf_chat_message.js`)

4. **Currency Handling**:
   - Portfolio supports multi-currency via ERPNext exchange rates
   - Financial periods store currency in `CF Security.currency` (inherited from yfinance)

## Key Files to Reference

**Financial Data Pipeline**:
- `cognitive_folio/doctype/cf_financial_period/cf_financial_period.py` - Auto-calculation logic
- `cognitive_folio/utils/sec_edgar_fetcher.py` - SEC Edgar XBRL parsing
- `cognitive_folio/doctype/cf_security/cf_security.py` - `fetch_fundamentals()` method

**AI Integration**:
- `cognitive_folio/doctype/cf_chat_message/cf_chat_message.py` - AI prompt assembly + streaming
- `cognitive_folio/utils/helper.py` - Template variable replacement

**Portfolio Management**:
- `cognitive_folio/doctype/cf_portfolio/cf_portfolio.py` - `calculate_rebalancing()` logic
- `cognitive_folio/doctype/cf_portfolio_holding/cf_portfolio_holding.py` - Real-time P&L calculation

---

**When extending this codebase**: Follow Frappe's DocType-first approach. New features typically require: (1) Create DocType via Desk UI, (2) Add Python controller methods, (3) Add JavaScript form customizations, (4) Wire up with `@frappe.whitelist()` if client needs access.

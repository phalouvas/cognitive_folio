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

### Comprehensive Data Validation Testing

**Financial Period Data Validator** - Automated testing for data completeness and prompt variables:

The `FinancialPeriodDataValidator` class in `test_cf_financial_period.py` provides comprehensive validation:

1. **Fundamental Data Fetching**: Tests SEC Edgar/Yahoo Finance import
2. **Data Completeness**: Validates all critical fields across annual/quarterly periods
3. **Prompt Variable Replacement**: Tests all `{{variable}}` patterns used in AI prompts
4. **Diagnostic Reporting**: Provides clear, actionable reports for AI agents

**Quick Validation (Frappe Console)**:
```bash
bench console
>>> from cognitive_folio.cognitive_folio.doctype.cf_financial_period.test_cf_financial_period import validate_security_data
>>> result = validate_security_data("AAPL")
>>> print(result['report'])
```

**Programmatic Validation**:
```python
from cognitive_folio.cognitive_folio.doctype.cf_financial_period.test_cf_financial_period import FinancialPeriodDataValidator

# Initialize validator for any symbol
validator = FinancialPeriodDataValidator("MSFT")

# Run full validation suite
result = validator.run_full_validation()

# Get diagnostic report
report = validator.get_diagnostic_report(result)
print(report)

# Access structured results
if result['success']:
    print("✓ All validations passed")
    print(f"Annual periods: {result['fetch_result']['period_counts']['annual']}")
    print(f"Quarterly periods: {result['fetch_result']['period_counts']['quarterly']}")
else:
    print("✗ Validation issues found:")
    for issue in result['data_validation']['issues']:
        print(f"  • {issue}")
```

**What the Validator Tests**:

1. **Security Setup**:
   - Gets existing or creates new CF Security for the symbol
   - Returns security name, country, SEC CIK status

2. **Fundamental Fetch**:
   - Triggers `fetch_data(with_fundamentals=True)`
   - Captures data source used (SEC Edgar vs Yahoo Finance)
   - Counts created annual/quarterly periods
   - Reports success/failure with details

3. **Data Completeness Validation**:
   - **Critical Fields** (must be >70% populated):
     - Income Statement: `total_revenue`, `net_income`, `operating_income`
     - Balance Sheet: `total_assets`, `total_liabilities`, `shareholders_equity`
     - Cash Flow: `operating_cash_flow`
     - Calculated Metrics: `gross_margin`, `net_margin`, `roe`
   - **Period Targets**:
     - Annual: 10+ periods (warns if <3)
     - Quarterly: 16 periods (warns if <8)
   - **Field Coverage**: Percentage of periods with each field populated

4. **Prompt Variable Replacement Tests**:
   Tests all variable patterns used in AI prompts:
   - Basic fields: `{{security_name}}`, `{{symbol}}`, `{{current_price}}`
   - JSON navigation: `{{ticker_info.marketCap}}`, `{{ticker_info.trailingPE}}`
   - Period tags: `{{periods:annual:10:markdown}}`, `{{periods:quarterly:16:markdown}}`
   - Comparisons: `{{periods:compare:latest_annual:previous_annual}}`
   - Validates output type, non-empty, minimum length

**Understanding Test Results**:

```
STATUS: PASS/FAIL
Security: AAPL (Apple Inc.)
Data Source: SEC Edgar

PERIOD COUNTS:
  Annual Periods: 10 (Target: 10+)       ← ✓ Good: 10+ years of data
  Quarterly Periods: 16 (Target: 16)     ← ✓ Good: 16 quarters
  Total Periods: 26

DATA QUALITY:
  Critical Fields: ✓ OK                  ← All required fields >70% populated
  Issues Found: 0

VARIABLE REPLACEMENT TESTS:
  Tests Passed: 12/12                    ← All prompt variables work
  Success Rate: 100.0%
  Status: ✓ ALL PASSED

FIELD COVERAGE BY CATEGORY:
  Income Statement:
    ✓ total_revenue: 100% (26/26)
    ✓ net_income: 100% (26/26)
    ✓ operating_income: 96% (25/26)
  Balance Sheet:
    ✓ total_assets: 100% (26/26)
    ✓ shareholders_equity: 100% (26/26)
```

**Common Issues and Solutions**:

| Issue | Cause | Solution |
|-------|-------|----------|
| "Only 3 annual periods (target: 10+)" | Yahoo Finance limited history | US stocks: Check SEC CIK populated; Non-US: Expected limitation |
| "Only 8 quarterly periods (target: 16)" | Insufficient historical data | Same as above; for non-US this is expected |
| "total_revenue only 45% populated" | Data source missing key fields | Check `data_source` and `data_quality_score` in periods; may need manual correction |
| "periods:annual:10:markdown test failed" | Not enough periods available | Fetch will succeed but AI analysis will note "incomplete history" |
| "ticker_info.marketCap output empty" | Ticker info not fetched | Run `fetch_data(with_fundamentals=False)` to update current price/info |

**AI Agent Testing Workflow**:

When an AI agent needs to validate data for analysis:

1. **Run validation** for target security:
   ```python
   result = validate_security_data("SYMBOL")
   ```

2. **Check overall status**:
   ```python
   if result['validation_result']['success']:
       # All systems go for AI analysis
   else:
       # Review issues before proceeding
   ```

3. **Interpret diagnostic report**:
   - `STATUS: PASS` → Safe to proceed with AI analysis
   - `STATUS: FAIL` → Review recommendations before analysis
   
4. **Address issues**:
   - Period count low? Expected for non-US; note in AI summary
   - Field coverage low? Check data source quality; may need supplemental data
   - Variable tests failed? Specific prompt variables won't work; adjust template

5. **Use in AI prompt preparation**:
   - Validation confirms which `{{periods:...}}` tags will have data
   - Field coverage indicates which metrics are reliable
   - Test output shows actual rendered variable content

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
- Validate period data: Use `FinancialPeriodDataValidator` for comprehensive checks

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

## Sector Coverage & Testing Guidance

### Current Inventory Snapshot
- 15 CF Securities currently carry a `sec_cik` and therefore exercise the SEC Edgar pipeline (examples: `CL`, `CVX`, `GOOGL`, `JNJ`, `JPM`, `PFE`, `V`, `XOM`).
- 68 additional stock records have no CIK on file and will continue to rely on Yahoo Finance fundamentals until a CIK is entered (includes US tickers such as `BAC`, `BLK`, `DLR`, `GS`, `KO`, `KHC`, `O`, alongside the broader European/Asia universe such as `SAP.DE`, `ENGI.PA`, `TSM`, `HSBA.L`).
- 11 non-stock instruments (`security_type` of Cash, Treasury Rate, ETF, etc.) are out of scope for SEC ingestion; treat them as quote-only data sources.
- Expect European listings (AMS, GER, PAR, LSE, HKG, etc.) to remain non-SEC; document this explicitly in testing notes so agents do not chase missing filings.
- **CIK maintenance**: When a US stock lacks `sec_cik`, call `CFSecurity._fetch_sec_cik_for_ticker()` (available in `cf_security.py`) to pull the value from the SEC ticker registry, `db_set` it on the document, and `frappe.db.commit()`. Without a populated CIK the SEC pipeline will never run for that ticker.

### Sector-Aware Mapping Plan
- **Detection**: Use `CF Security` metadata (`sector`, `industry`, `security_type`, `stock_exchange`, `sec_cik`) to decide which mapping profile to apply. Default to the broad profile when the sector is missing.
   - Heuristics now live in `_determine_sector_profile()` inside `utils/sec_edgar_fetcher.py`. It falls back to the general profile unless keywords such as “bank”, “insurance”, “utility”, “energy/materials”, or “REIT” appear in the sector/industry/name fields for stock securities.
- **Profiles**: Maintain mapping dictionaries inside `utils/sec_edgar_fetcher.py` for each major sector family:
   1. General/Industrial/Technology (current behavior – revenue/COGS/operating_income flow-down).
   2. Banks & Diversified Financials (focus on net interest income, provision for credit losses, deposits, loans, CET1, efficiency ratio; derive revenue from interest + non-interest components when GAAP tags differ).
   3. Insurance (premiums written/earned, combined ratio inputs, claims, investment income).
   4. Energy & Materials (production costs, lifting costs, proved reserves where available, capex split).
   5. Utilities & Infrastructure (regulated vs unregulated revenue, capex, rate-base indicators).
   6. REITs (FFO/AFFO, NOI, occupancy, same-store metrics, maintenance capex).
   7. Asset-light/Service sectors (consumer staples/discretionary, healthcare, telco) continue to use the general mapping but add well-known aliases (e.g., `us-gaap:NetSales`, `us-gaap:SalesRevenueNet`).
- **Fallback Rules**: When a sector-specific tag is not present in a filing, gracefully fall back to the general tag list instead of leaving fields empty. Always respect `data_quality_score` so a lower-quality Yahoo import does not overwrite a higher-quality SEC pull.
- **Documentation**: Each mapping profile should carry inline comments indicating the GAAP tags covered plus derived formulas (e.g., “Banks: `interest_income_total = interestIncome + interestIncomeAfterProvision`”). Keep the guide updated whenever a new alias is added.

### Representative Regression Tests
- Run the `FinancialPeriodDataValidator` after every mapping change against at least one security per sector profile:
   - Technology/General: `AAPL`, `GOOGL`, `MSFT` (SEC) and `SAP.DE`, `TSM` (Yahoo fallback).
   - Banking: `JPM`, `BAC`, `GS` (SEC once CIKs are populated) plus `HSBA.L` as the non-SEC control.
   - Insurance: `ALV.DE`, `HNR1.DE` (Yahoo) and `PFG`, `MET` once US insurers are added to the database.
   - Energy/Materials: `XOM`, `CVX` (SEC) and `RWE.DE`, `TTE.PA` (Yahoo).
   - REIT/Utilities: `O`, `DLR` (needs CIKs) and `VNA.DE`, `TRN.MI` for international coverage.
   - Consumer Staples/Healthcare: `JNJ`, `PFE`, `KO`, `SBUX` (some missing CIKs today) plus `NESN.SW`, `HEIA.AS`.
- Note in commit/test descriptions whether a validation failure is due to true data gaps (e.g., European listings never hitting SEC) versus a missing mapping. This makes it clear to future agents when gaps are intentional.

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

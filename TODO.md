# Cognitive Folio - Structured Financial Data Implementation

This document tracks the migration from JSON blob storage to structured CF Financial Period DocType for financial statement data. This enables better AI analysis, historical tracking, and data quality management.

## Context

Previously, financial data from Yahoo Finance was stored as JSON blobs in Long Text fields (profit_loss, balance_sheet, cash_flow). This made it difficult for AI to access data consistently and impossible to track history or compare companies effectively.

The new **CF Financial Period** DocType stores financial data in structured fields with automatic calculations for margins, ratios, and YoY growth. It supports multiple data sources (Yahoo Finance, PDF uploads, manual entry) with a conflict resolution system that prioritizes higher-quality sources.

---

## Implementation Status

### ✅ Phase 1: Foundation (COMPLETED)

#### Task 1.1: Create CF Financial Period DocType ✓
**Status:** COMPLETED  
**Details:** 
- Created `/cognitive_folio/doctype/cf_financial_period/` with JSON, Python, JS, and test files
- Fields include: security link, period identification (fiscal_year, quarter, type), income statement (revenue, expenses, income), balance sheet (assets, liabilities, equity), cash flow (operating, investing, financing), computed metrics (margins, ratios), growth metrics (YoY comparisons)
- Auto-naming: `{security}-{period_type}-{fiscal_year}-{fiscal_quarter}`
- Automatic calculation of margins (gross, operating, net), ratios (ROE, ROA, debt/equity, current, quick), YoY growth when previous period exists

#### Task 1.2: Add Smart Conflict Resolution ✓
**Status:** COMPLETED  
**Details:**
- Added fields: `override_yahoo` (checkbox to lock data), `data_quality_score` (auto-calculated: Manual=100, PDF=95, SEC=90, Yahoo=85), `verified_by_pdf` (attachment to source document)
- Created `get_source_priority()` function to rank data sources
- Created `check_import_conflicts()` function to detect existing higher-quality periods before import
- Modified `import_from_yahoo_finance()` to accept `replace_existing` and `respect_override` parameters
- Import logic now: checks existing periods, compares quality scores, skips if existing is higher priority, updates if replace_existing=True, respects override_yahoo flag
- JavaScript dialog shows conflicts with table of existing periods and their sources/quality scores
- Import results show: imported count, updated count, skipped count

#### Task 1.3: Create Import from Yahoo Finance ✓
**Status:** COMPLETED  
**Details:**
- Function: `import_from_yahoo_finance(security_name, replace_existing=False, respect_override=True)`
- Maps Yahoo Finance field names to CF Financial Period fields using field_mapping dict
- Processes both Annual and Quarterly data from existing JSON blobs
- Stores raw JSON in raw_income_statement, raw_balance_sheet, raw_cash_flow for audit trail
- Handles ticker_info for shares_outstanding
- Returns success status with counts and errors array
- Button added to CF Security form: "Actions → Import to Financial Periods"

---

### 🔄 Phase 2: AI Integration (IN PROGRESS)

#### Task 2.1: Create Helper Function for AI Queries
**Status:** NOT STARTED  
**Priority:** HIGH (Foundation for all AI improvements)  
**Location:** `cognitive_folio/doctype/cf_financial_period/cf_financial_period.py`  
**Details:**
- Create `format_periods_for_ai(security_name, period_type="Annual", num_periods=4, include_growth=True, format="markdown")`
- Returns formatted text/markdown with financial data ready for AI consumption
- Should include: income statement summary, balance sheet key items, cash flow metrics, computed ratios, growth rates
- Support filtering by period_type (Annual/Quarterly/TTM), date range, specific fiscal years
- Add optional `fields` parameter to select specific metrics only
- Format options: "markdown", "text", "json", "table"
- Example output format shown in FINANCIAL_PERIODS.md

#### Task 2.2: Update CF Security AI Prompt
**Status:** NOT STARTED  
**Priority:** HIGH (Most frequently used feature)  
**Location:** `cognitive_folio/doctype/cf_security/cf_security.py`  
**Function:** `process_security_ai_suggestion(security_name, user)`  
**Current:** Parses JSON blobs with `json.loads(security.profit_loss)`, uses regex to replace variables like `{{field_name}}`  
**Changes Needed:**
- Replace JSON parsing with `format_periods_for_ai()` call
- Update ai_prompt template in CF Settings to use new structured data references
- Add support for period-specific variables: `{{periods:annual:5}}`, `{{periods:quarterly:4}}`
- Keep backward compatibility with existing JSON fields during transition
- Test with multiple securities to ensure accuracy matches previous approach

#### Task 2.3: Update CF Portfolio AI Analysis
**Status:** NOT STARTED  
**Priority:** HIGH  
**Location:** `cognitive_folio/doctype/cf_portfolio/cf_portfolio.py`  
**Functions:** `process_portfolio_ai_analysis()`, `process_evaluate_holdings_news()`  
**Current:** Aggregates data from holdings using JSON parsing  
**Changes Needed:**
- Query CF Financial Period for all holdings in portfolio
- Aggregate metrics: total revenue, weighted average margins, portfolio-level ratios
- Format summary for AI: portfolio composition, sector allocation, financial health metrics
- Add comparison: best/worst performers by revenue growth, margin trends, etc.
- Use `format_periods_for_ai()` for individual holdings when needed

#### Task 2.4: Update CF Chat Message Context
**Status:** NOT STARTED  
**Priority:** MEDIUM  
**Location:** `cognitive_folio/doctype/cf_chat_message/cf_chat_message.py`  
**Function:** `prepare_prompt(portfolio, security)`  
**Current:** Uses regex `\(\((\w+)\)\)` to replace variables from document fields  
**Changes Needed:**
- Add special handling for financial period variables: `((periods:last_4_quarters))`, `((periods:annual:5))`, `((periods:latest))`
- When security context exists, automatically include latest financial period summary
- When portfolio context exists, include portfolio-level aggregated metrics
- Add period comparison syntax: `((periods:compare:2024Q3:2024Q2))`
- Update helper.py `replace_variables()` to recognize period syntax

---

### 🔧 Phase 3: Automation & Data Entry (MEDIUM PRIORITY)

#### Task 3.1: Auto-Import on Fetch Data
**Status:** NOT STARTED  
**Location:** `cognitive_folio/doctype/cf_security/cf_security.py`  
**Function:** `fetch_data(with_fundamentals=False)`  
**Changes Needed:**
- After successful Yahoo Finance fetch with fundamentals=True, automatically call `import_from_yahoo_finance(self.name)`
- Add setting in CF Settings: "Auto Import Financial Periods" (default: True)
- Show notification: "Financial data fetched and imported to X periods"
- Handle errors gracefully, don't fail main fetch if import has issues
- Log any import warnings/errors for user review

#### Task 3.2: PDF Financial Statement Parser
**Status:** NOT STARTED  
**Priority:** MEDIUM  
**Location:** New file `cognitive_folio/utils/pdf_financial_parser.py`  
**Dependencies:** Existing pdfplumber integration in cf_chat_message.py  
**Requirements:**
- Function: `parse_financial_pdf(pdf_path, security_name, period_type, fiscal_year, fiscal_quarter=None)`
- Detect financial statement tables (Income Statement, Balance Sheet, Cash Flow)
- Extract line items using table recognition patterns
- Map extracted values to CF Financial Period fields
- Handle multiple formats: 10-Q, 10-K, annual reports, different layouts
- Return dict ready for CF Financial Period creation with data_source="PDF Upload"
- Store original PDF as attachment in verified_by_pdf field
- UI: Add "Upload Financial Statement" button in CF Security form
- Show parsing preview before creating period

#### Task 3.3: Manual Data Entry Improvements
**Status:** NOT STARTED  
**Location:** `cognitive_folio/doctype/cf_financial_period/cf_financial_period.js`  
**Enhancements:**
- Add "Copy from Previous Period" button (copies previous year/quarter data for editing)
- Quick-entry template with common fields only (revenue, income, assets, equity, cash flow)
- Validation warnings: negative equity, margins >100%, revenue<0, debt/equity>10
- Auto-calculate missing fields: gross_profit = revenue - cost_of_revenue
- Show side-by-side comparison with previous period while editing
- Add "Estimate" checkbox for projected/guidance figures

#### Task 3.4: Bulk Import Utility
**Status:** NOT STARTED  
**Location:** `cognitive_folio/doctype/cf_security/cf_security_list.js`  
**Requirements:**
- Add list view action: "Import All to Financial Periods"
- Multi-select securities, click action to batch import
- Show progress dialog with progress bar
- Process securities one by one, show status for each
- Summary report: X successful, Y failed, Z skipped
- Option to continue on errors or stop on first error
- Export error log if failures occur

---

### 📊 Phase 4: Reporting & Visualization (LOWER PRIORITY)

#### Task 4.1: Financial Period Comparison Report
**Status:** NOT STARTED  
**Location:** New folder `cognitive_folio/report/financial_period_comparison/`  
**Type:** Frappe Report (query-based or script)  
**Features:**
- Filter by: security, period_type, date range, fiscal years
- Columns: Period, Revenue, Growth%, Net Income, Margins, ROE, FCF
- Show trends with sparklines (▁▂▃▅▇)
- Highlight: positive growth (green), negative (red), best/worst performers
- Export to Excel with charts
- Drill-down: click period to open CF Financial Period form

#### Task 4.2: Multi-Security Comparison Report
**Status:** NOT STARTED  
**Location:** New folder `cognitive_folio/report/security_comparison/`  
**Type:** Frappe Report  
**Features:**
- Compare multiple securities side-by-side (peer analysis)
- Use latest available period for each security
- Columns: Security, Revenue, Rev Growth, Margins, ROE, ROA, Debt/Equity, Valuation multiples
- Filter by: sector, region, market cap range
- Sortable by any metric
- Add to portfolio feature from report
- Sector/industry averages row

#### Task 4.3: Financial Metrics Dashboard
**Status:** NOT STARTED  
**Location:** New folder `cognitive_folio/dashboard/financial_metrics/`  
**Type:** Custom Page with Chart.js  
**Features:**
- Line charts: Revenue trend, Margin trends (gross, operating, net), Cash flow trend
- Bar charts: Quarterly comparison, YoY growth rates
- Gauge charts: Current ratios (ROE, ROA, Debt/Equity)
- Time period selector: 1Y, 3Y, 5Y, All
- Compare mode: overlay multiple securities
- Drill-down: click data point to see period details
- Export chart as image

---

### 🚀 Phase 5: Advanced Features (FUTURE)

#### Task 5.1: Data Freshness Indicators
**Status:** NOT STARTED  
**Location:** `cognitive_folio/doctype/cf_security/cf_security.py`  
**Changes:**
- Add fields: `last_financial_period_date` (Date), `days_since_last_period` (Int), `needs_update` (Check)
- Compute in `on_update()`: query latest CF Financial Period date, calculate days since
- Set needs_update=True if: days > 90 for quarterly, days > 365 for annual
- Display warning banner in CF Security form: "⚠️ Financial data is 95 days old. Consider updating."
- Color-code in list view: green (<30 days), yellow (30-90 days), red (>90 days)
- Add filter: "Needs Financial Update"

#### Task 5.2: Valuation Using Structured Data
**Status:** NOT STARTED  
**Location:** `cognitive_folio/doctype/cf_security/cf_security.py`  
**Functions:** `_calculate_dcf_value()`, `_calculate_residual_income()`, etc.  
**Current:** Parses JSON blobs: `json.loads(self.cash_flow)`, iterates over dates  
**Changes:**
- Replace JSON parsing with CF Financial Period queries
- Query: `frappe.get_all("CF Financial Period", filters={...}, fields=[...], order_by="fiscal_year DESC", limit=5)`
- Cleaner code, easier to read and maintain
- Better performance (indexed queries vs JSON parsing)
- Use latest available data automatically

#### Task 5.3: Period-over-Period Chat Comparisons
**Status:** NOT STARTED  
**Location:** `cognitive_folio/doctype/cf_chat_message/cf_chat_message.py`  
**Requirements:**
- Detect queries: "compare Q3 vs Q2", "show last 5 years trends", "how did revenue change?"
- Parse natural language to extract: periods to compare, metrics of interest
- Query relevant CF Financial Period records
- Format comparison table for AI consumption
- Example: "Q3 2024 vs Q2 2024: Revenue +8%, Net Income +12%, Margins stable"

---

### 📚 Phase 6: Documentation & Cleanup (FINAL)

#### Task 6.1: Update Main README
**Status:** NOT STARTED  
**Location:** `README.md`  
**Requirements:**
- Add section: "Financial Data Architecture"
- Explain CF Financial Period DocType and benefits
- Quick start guide: how to import data, view periods, run reports
- Screenshots of key features: import dialog, period form, comparison report
- API examples for developers: querying periods, formatting for AI
- Link to architecture docs if needed

#### Task 6.2: Consolidate and Cleanup Documentation
**Status:** NOT STARTED  
**Actions:**
- Review FINANCIAL_PERIODS.md content
- Merge relevant sections into README.md under new "Financial Data" section
- Delete FINANCIAL_PERIODS.md (temporary implementation doc)
- Delete TODO.md (this file, once all tasks complete)
- Update any references in code comments to point to README
- Ensure all examples in README are tested and accurate

---

## Testing Checklist

Before marking implementation complete, verify:

- [ ] Import from Yahoo Finance works for both Annual and Quarterly periods
- [ ] Conflict resolution correctly skips higher-priority sources
- [ ] AI prompts use CF Financial Period data and produce accurate analysis
- [ ] Manual data entry validates and calculates metrics correctly
- [ ] Reports show accurate comparisons and trends
- [ ] Performance is acceptable with 100+ securities, 1000+ periods
- [ ] Documentation is complete and examples work

---

## Migration Notes

- Keep JSON blob fields during transition (profit_loss, balance_sheet, cash_flow)
- Both systems run in parallel initially
- Gradually migrate AI prompts to use CF Financial Period
- Once confident (3-6 months), deprecate JSON blob fetching
- Final cleanup: remove JSON blob fields from CF Security

---

## Key Files Modified/Created

### New Files:
- `cognitive_folio/doctype/cf_financial_period/cf_financial_period.json`
- `cognitive_folio/doctype/cf_financial_period/cf_financial_period.py`
- `cognitive_folio/doctype/cf_financial_period/cf_financial_period.js`
- `cognitive_folio/doctype/cf_financial_period/test_cf_financial_period.py`

### Modified Files:
- `cognitive_folio/doctype/cf_security/cf_security.js` - Added import button and conflict dialog
- (To be modified in Phase 2+): cf_security.py, cf_portfolio.py, cf_chat_message.py

### Utility Files:
- (To be created): `cognitive_folio/utils/pdf_financial_parser.py`

---

**Last Updated:** 2024-11-17  
**Current Phase:** Phase 2 - AI Integration  
**Next Task:** Task 2.1 - Create Helper Function for AI Queries

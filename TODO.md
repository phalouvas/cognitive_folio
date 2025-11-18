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

#### Task 2.1: Create Helper Function for AI Queries ✓
**Status:** COMPLETED  
**Priority:** HIGH (Foundation for all AI improvements)  
**Location:** `cognitive_folio/doctype/cf_financial_period/cf_financial_period.py`  
**Details:**
- Created `format_periods_for_ai(security_name, period_type="Annual", num_periods=4, include_growth=True, format="markdown")`
- Returns formatted text/markdown with financial data ready for AI consumption
- Includes: income statement summary, balance sheet key items, cash flow metrics, computed ratios, growth rates
- Supports filtering by period_type (Annual/Quarterly/TTM), date range, specific fiscal years
- Optional `fields` parameter to select specific metrics only
- Format options: "markdown", "text", "json", "table"
- Thoroughly tested with real and edge case data; output matches requirements

#### Task 2.2: Update CF Security AI Prompt ✓
**Status:** COMPLETED  
**Priority:** HIGH (Most frequently used feature)  
**Location:** `cognitive_folio/doctype/cf_security/cf_security.py`  
**Function:** `process_security_ai_suggestion(security_name, user)`  
**Details:**
- Updated to support `{{periods:annual:5}}`, `{{periods:quarterly:4}}`, etc. using `format_periods_for_ai()`
- Regex now detects and replaces period variables with formatted structured data
- Legacy JSON field variables still supported for backward compatibility
- Tested with multiple securities and prompt templates for accuracy

#### Task 2.3: Update CF Portfolio AI Analysis ✓
**Status:** COMPLETED  
**Priority:** HIGH  
**Location:** `cognitive_folio/doctype/cf_portfolio/cf_portfolio.py`  
**Functions:** `process_portfolio_ai_analysis()`, `build_portfolio_financial_summary()`, `test_portfolio_prompt_expansion()`  
**Details:**
- Implemented `build_portfolio_financial_summary()` generating: total revenue, weighted gross/operating/net margins (properly scaled from stored decimals), total operating & free cash flow, average ROE, average debt/equity, revenue growth ranking (top & lowest), sector allocation block.
- Injects summary block ahead of holdings in both analysis flow and test helper; confirmed presence of lines (Weighted Gross Margin, Growth Ranking, Sector Allocation) via console test.
- Fixed field usage (`total_revenue` instead of non-existent `revenue`); corrected worst_growth logic; applied percentage scaling (*100) for margins and ROE to match period display formatting.
- Holding-level periods expansion uses existing `format_periods_for_ai()` ensuring consistent formatting across security and portfolio contexts.
- Added test helper `test_portfolio_prompt_expansion()` for deterministic verification without invoking external AI.
**Follow-Ups (Deferred):** snapshot caching on portfolio doc, batch query optimization, extended ranking (margin expansion, ROE ordering). These can be scheduled as minor enhancements without blocking Task 2.4.

#### Task 2.4: Update CF Chat Message Context ✓
**Status:** COMPLETED  
**Priority:** MEDIUM  
**Location:** `cognitive_folio/doctype/cf_chat_message/cf_chat_message.py`  
**Function:** `prepare_prompt(portfolio, security)`  
**Details:** Implemented periods syntax for security (`{{periods:annual:3}}`, quarterly, ttm) and portfolio (`((periods:annual:3))`, `((periods:latest))`). Latest shorthand produces portfolio summary plus latest annual + last 4 quarterly per holding. Fallback messages for missing contexts. Regex replacements centralized with error logging.

#### Task 2.5: Chat Period Comparisons ✓
**Status:** COMPLETED  
**Priority:** MEDIUM  
**Location:** `cognitive_folio/doctype/cf_chat_message/cf_chat_message.py`  
**Function:** `prepare_prompt(portfolio, security)`  
**Details:** Added comparison syntax for security `{{periods:compare:2025:2024}}` and portfolio `((periods:compare:2025:2024))` including revenue & net income change %, margin point deltas, and aggregate weighted gross margin Δ for portfolio. Quarterly variants supported (e.g. `((periods:compare:2024Q3:2024Q2))`). Natural language parsing of “compare Q3 vs Q2” remains future (see Phase 5.3).

---

### 🔧 Phase 3: Automation & Data Entry (MEDIUM PRIORITY)

#### Task 3.1: Auto-Import on Fetch Data ✓
**Status:** COMPLETED  
**Location:** `cognitive_folio/doctype/cf_security/cf_security.py`  
**Function:** `fetch_data(with_fundamentals=False)`  
**Details:**
- Added `auto_import_financial_periods` checkbox field to CF Settings (default: 1/True)
- Auto-import triggers AFTER saving fundamentals to ensure JSON blobs exist
- Result stored in `last_period_import_result` field (Long Text) for audit trail
- User notification shows: "X new, Y updated, Z skipped" via msgprint with green indicator
- Errors logged to Error Log and shown as orange warning notification without failing main fetch
- Uses `db_set()` to persist result without triggering full save cycle
- Respects conflict resolution (skips higher-quality existing periods)

#### Task 3.2: PDF Financial Statement Parser
**Status:** ✅ COMPLETED  
**Priority:** MEDIUM  
**Location:** `cognitive_folio/utils/pdf_financial_parser.py`  
**Dependencies:** Existing pdfplumber integration in cf_chat_message.py  
**Implementation Summary:**
- ✅ Created `parse_financial_pdf(security, file_path, period_type, data_source)` function
- ✅ Table detection functions: `_find_income_statement()`, `_find_balance_sheet()`, `_find_cash_flow_statement()`
- ✅ Period label parsing with regex patterns (handles 2024, Q3 2024, December 31 2024, etc.)
- ✅ Financial value parsing: billions/millions suffixes (1.2B, 45.6M), parentheses for negatives
- ✅ Field mapping via `_map_label_to_field()` with keyword matching for income/balance/cash flow
- ✅ Data merging from multiple statement tables into unified period records
- ✅ Quality score 90 (higher than Yahoo 70, lower than verified 100)
- ✅ Respects existing higher-quality periods, updates lower-quality ones
- ✅ Whitelisted `upload_and_parse_financial_pdf()` method for client calls
- ✅ UI: "Upload Financial Statement" button in CF Security Actions menu
- ✅ Dialog with Attach field, period type selector, helpful format instructions
- ✅ Success/error messaging with import counts, auto-reload after import
- ✅ Comprehensive error handling and logging

**Note:** Future enhancement: attach original PDF to `verified_by_pdf` field for audit trail

#### Task 3.3: Manual Data Entry Improvements
**Status:** ✅ COMPLETED  
**Location:** `cognitive_folio/doctype/cf_financial_period/cf_financial_period.js` + `.py`  
**Implementation Summary:**
- ✅ "Copy from Previous Period" button with selective field copying (Income/Balance/Cash Flow)
- ✅ Period comparison dialog showing side-by-side metrics with % change
- ✅ Validation warnings: negative equity, margins >100%, revenue<0, debt/equity>10x, negative current ratio
- ✅ Auto-calculate missing fields: gross profit, operating income, free cash flow, cost of revenue
- ✅ Quick-entry hint for new records: "Fill in Revenue, Net Income, Assets for basic analysis"
- ✅ Color-coded comparison (green positive, red negative changes)
+ ✅ Server-side `get_previous_period()` method with quarterly progression logic
+ ✅ Dashboard alerts for validation warnings (yellow indicator)
+ ✅ Auto-calculate shows blue alert with calculated field names
+
+**Features:**
+- Previous period detection handles Q1→Q4 of previous year, Q2→Q1, etc.
+- Comparison table organized by sections: Income Statement, Margins, Balance Sheet, Cash Flow, Ratios
+- Values formatted with M/B suffixes for readability
+- Optional field copy allows cherry-picking data from previous period

#### Task 3.4: Bulk Import Utility
**Status:** COMPLETED  
**Location:** `cognitive_folio/doctype/cf_security/cf_security_list.js` & server method in `cf_financial_period.py`  
**Implementation Summary:**
- Added list view action "Bulk Import Periods" for multi-selected securities.
- Dialog options: Replace Existing Periods, Respect Override Yahoo, Stop on First Error.
- Server method `bulk_import_financial_periods` enhanced with realtime progress events (`progress_id` channel) and stop-on-error logic.
- Progress dialog shows per-security status (imported, updated, skipped, errors) and dynamic progress bar.
- Final summary includes aggregate counts and abort indication if stopped early.
- Provides JSON download of detailed results for audit/troubleshooting.
- Respects existing conflict resolution (override_yahoo, data source priority via underlying import function).
- Error handling: logs to Error Log, continues unless stop-on-error selected.
 - Added background enqueue support (`enqueue_bulk_import_financial_periods`) with polling retrieval (`get_bulk_import_job_result`).
 - Implemented daily scheduled task `daily_bulk_import_all_securities` registered in `hooks.py` (non-destructive: replace_existing=False, respect_override=True).
 - Added second list action "Enqueue Bulk Import (Background)" allowing import of all securities or selection without blocking UI.
**Next Enhancements (Optional):** enqueue as background job for very large batches; add filtering (sector/portfolio) mass selection.

---

### 📊 Phase 4: Reporting & Visualization (LOWER PRIORITY)

#### Task 4.1: Financial Period Comparison Report
**Status:** COMPLETED  
**Location:** `cognitive_folio/report/financial_period_comparison/`  
**Type:** Script Report  
**Implementation Summary:**
- Created script report with filters: Security (optional), Period Type (Annual/Quarterly), Number of Periods (default 5).
- Columns: Security, Period, Revenue, Revenue Growth %, Net Income, Net Income Growth %, EPS, Gross Margin %, Operating Margin %, ROE %, Free Cash Flow, FCF Growth %, Trend (Sparkline).
- Sparkline: SVG chart showing Revenue (blue) and Net Income (green) trends over periods.
- Formatting: Currency fields formatted with symbols, percentages colored (green positive, red negative).
- Drill-down: "View Period Details" button to open CF Financial Period form.
- Export: Placeholder for Excel with charts (future enhancement).
- Data processing: Groups periods by security, limits to specified number, sorts chronologically for trends.

#### Task 4.2: Multi-Security Comparison Report
**Status:** COMPLETED  
**Location:** `cognitive_folio/report/security_comparison/`  
**Type:** Script Report  
**Implementation Summary:**
- Created peer analysis report with filters: Sector, Region, Min/Max Market Cap, Period Type.
- Columns: Security, Sector, Latest Period, Revenue, Revenue Growth %, Net Income, Gross/Operating Margins, ROE/ROA %, Debt/Equity, Current Ratio, Free Cash Flow, Market Cap, P/E Ratio.
- Uses latest available period per security for comparison.
- Sector averages row: calculates averages for sectors with multiple securities.
- Formatting: Currency fields formatted, percentages colored (green positive, red negative), sector averages bolded.
- Actions: "Add to Portfolio" (select securities, choose portfolio, set quantity), "View Security Details" (drill-down to CF Security form).
- Data processing: Filters securities by criteria, fetches latest period data, calculates P/E ratio.

#### Task 4.3: Financial Metrics Dashboard
**Status:** COMPLETED  
**Location:** `cognitive_folio/dashboard/financial_metrics/`  
**Type:** Custom Page with Frappe Charts  
**Implementation Summary:**
- Created custom dashboard page with filters: Security (required), Period Type (Annual/Quarterly), Years (1/3/5/All).
- Charts: Revenue Trend (line), Margin Trends (line with gross/operating/net), Cash Flow Trend (line), Quarterly Comparison (bar), YoY Growth Rates (bar), Financial Ratios (gauge-style display).
- Data functions: `get_revenue_trend`, `get_margin_trends`, `get_cash_flow_trend`, `get_quarterly_comparison`, `get_yoy_growth_rates`, `get_financial_ratios`.
- Frontend: Interactive charts using Frappe Chart library, color-coded ratios (green/orange/red based on thresholds), responsive grid layout.
- Features: Refresh button, dynamic loading on filter changes, ratio color coding (e.g., ROE >10% green).
- Note: Compare mode and drill-down not implemented yet; export as image requires additional setup.

---

### ✅ Phase 5: Advanced Features (COMPLETED)

#### Task 5.1: Data Freshness Indicators ✓
**Status:** COMPLETED  
**Location:** `cognitive_folio/doctype/cf_security/cf_security.py` + `.js` + `_list.js`  
**Implementation Summary:**
- ✅ Added fields to CF Security: `last_financial_period_date` (Date), `days_since_last_period` (Int), `needs_update` (Check)
- ✅ Implemented `update_data_freshness()` method in `on_update()` hook
- ✅ Queries latest CF Financial Period date and calculates days since last update
- ✅ Sets `needs_update=True` if: days > 90 for quarterly, days > 365 for annual
- ✅ List view color coding: green (<30 days), orange (30-90 days), red (>90 days or needs_update)
- ✅ Added "Needs Financial Update" filter to list view menu
- ✅ Warning banner in form view: "⚠️ Financial data is X days old. Consider updating."

#### Task 5.2: Valuation Using Structured Data ✓
**Status:** COMPLETED  
**Location:** `cognitive_folio/doctype/cf_security/cf_security.py`  
**Functions Updated:** `_calculate_dcf_value()`, `_calculate_residual_income()`, `_calculate_pe_value()`, `_is_asset_heavy_business()`  
**Implementation Summary:**
- ✅ Created `_get_financial_periods()` helper method for efficient period queries
- ✅ Replaced all JSON parsing (`json.loads(self.cash_flow)`) with CF Financial Period queries
- ✅ Updated DCF calculation to use structured period data for FCF analysis
- ✅ Updated Residual Income model to use period ROE and shareholders_equity
- ✅ Updated P/E valuation to query latest annual period
- ✅ Updated asset turnover calculation in `_is_asset_heavy_business()`
- ✅ Cleaner code, better performance with indexed queries
- ✅ Automatic use of latest available data

#### Task 5.3: Period-over-Period Chat Comparisons ✓
**Status:** COMPLETED  
**Location:** `cognitive_folio/doctype/cf_chat_message/cf_chat_message.py`  
**Implementation Summary:**
- ✅ Added `detect_natural_language_comparisons()` method to parse comparison queries
- ✅ Detects patterns: "compare Q3 vs Q2", "compare 2024 to 2023", "compare Q3 2024 and Q2 2024"
- ✅ Supports quarterly comparisons: "Q3 vs Q2", with or without years
- ✅ Supports annual comparisons: "2024 vs 2023"
- ✅ Supports relative comparisons: "Q3 vs previous quarter", "2024 vs previous year"
- ✅ Automatically calculates previous periods (Q1 → Q4 of previous year, etc.)
- ✅ Transforms natural language to comparison syntax: `{{periods:compare:2024:2023}}`
- ✅ Works for both security and portfolio contexts
- ✅ Integrated with existing comparison formatting from Task 2.5

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
- `cognitive_folio/doctype/cf_security/cf_security.py` - Implemented periods variable expansion for AI prompts
- `cognitive_folio/doctype/cf_portfolio/cf_portfolio.py` - Added holding-level periods injection (aggregate pending)
- (Pending) `cognitive_folio/doctype/cf_chat_message/cf_chat_message.py` - To add periods support & comparisons

### Utility Files:
- (To be created): `cognitive_folio/utils/pdf_financial_parser.py`
- `cognitive_folio/www/variable_reference.md` - Public variable reference page (wrapped in `{% raw %}` to prevent Jinja parsing)

---

**Last Updated:** 2025-11-18  
**Current Phase:** Phase 2 - AI Integration  
**Next Task:** Task 3.4 - Bulk Import Utility

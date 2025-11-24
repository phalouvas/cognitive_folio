### Cognitive Folio

AI-Optimized Investing, Thoughtfully Engineered

---

## Table of Contents

- [Installation](#installation)
- [Financial Data Architecture](#financial-data-architecture)
- [Quick Start Guide](#quick-start-guide)
- [API & Developer Reference](#api--developer-reference)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app cognitive_folio
```

### Required Dependencies

```bash
# Core dependencies (required for all stocks)
cd frappe-bench
./env/bin/pip install yfinance openai

# SEC Edgar integration (required for US stocks only)
./env/bin/pip install sec-edgar-downloader python-xbrl lxml pdfplumber
```

---

## Financial Data Architecture

Cognitive Folio uses a **structured financial data system** built around the `CF Financial Period` DocType. This provides a queryable, consistent database for storing and analyzing financial statements - replacing the old approach of storing large JSON blobs.

### Current Scope: US Stocks Only for Regulatory Filings

⚠️ **Important**: The current implementation focuses on **US-listed companies** for SEC Edgar integration. This provides:
- **High-quality data** from regulatory filings (10-K, 10-Q) with quality score 95
- **Automatic XBRL parsing** from SEC Edgar inline XBRL HTML files
- **Fallback to Yahoo Finance** (quality score 85) for non-US stocks or when SEC data is unavailable

**Future Phases**: Integration with Hong Kong (HKEX), UK (Companies House), EU (ESEF), Canada (SEDAR+), Japan (EDINET), and Australia (ASIC) regulatory databases are planned but not yet implemented.

### Why Structured Financial Data?

**Benefits:**
- ✅ **Consistent Format** - All companies use the same field structure
- ✅ **Historical Tracking** - Built-in time series with automatic YoY growth calculations
- ✅ **AI Efficiency** - Clean queries reduce token usage and improve response speed
- ✅ **Automatic Calculations** - Margins, ratios, and growth metrics computed on save
- ✅ **Data Quality** - Type enforcement, validation rules, and audit trails
- ✅ **Multi-Source Support** - SEC Edgar (US only), Yahoo Finance (global), PDFs, or manual entry

### Core Components

#### CF Financial Period DocType

Stores individual financial reporting periods with:

**Period Identification:**
- Security reference
- Period type (Annual/Quarterly/TTM)
- Fiscal year and quarter
- Filing and period end dates
- Data source tracking

**Financial Statements:**
- **Income Statement**: Revenue, expenses, net income, EPS
- **Balance Sheet**: Assets, liabilities, equity
- **Cash Flow**: Operating, investing, financing cash flows

**Computed Metrics:**
- **Margins**: Gross, operating, net margins (%)
- **Profitability**: ROE, ROA
- **Leverage**: Debt-to-equity ratio
- **Liquidity**: Current ratio, quick ratio
- **Growth**: YoY revenue, income, EPS, FCF growth

#### Data Quality System

**Source Priority Hierarchy:**
1. **Manual Entry** (Score: 100) - User-verified data
2. **SEC Edgar** (Score: 95) - US regulatory filings (10-K, 10-Q)
3. **PDF Upload** (Score: 95) - Official documents
4. **Yahoo Finance** (Score: 85) - Third-party aggregator (global)

**Current Implementation:**
- **US Stocks**: Automatic SEC Edgar integration with XBRL parsing
- **Global Stocks**: Yahoo Finance fallback for all other markets
- **Future**: Hong Kong, UK, EU, Canada, Japan, Australia regulatory filings (Phase 3+)

**Conflict Resolution:**
- Higher-quality sources take precedence
- `override_yahoo` flag locks data from automatic updates
- Import operations respect existing higher-priority data
- SEC Edgar data automatically upgrades Yahoo Finance data for US companies

---

## Quick Start Guide

### 1. Fetch Financial Data

Navigate to a **CF Security** record and click:
- **Actions → Fetch Fundamentals**

The system automatically:
- **For US stocks**: Fetches from SEC Edgar (10-K, 10-Q filings) with XBRL parsing
- **For other stocks**: Falls back to Yahoo Finance
- Creates CF Financial Period records for each reporting period
- Calculates margins, ratios, and growth metrics
- Handles conflicts using quality scoring (SEC Edgar 95 > Yahoo 85)
- Auto-upgrades existing Yahoo data when SEC Edgar data becomes available

### 2. SEC Edgar Integration (US Stocks Only)

**Automatic Operation:**
- System automatically fetches SEC CIK (Central Index Key) for US-listed companies
- Downloads 10-K (annual) and 10-Q (quarterly) filings
- Parses inline XBRL data from HTML filings
- Maps US-GAAP taxonomy to CF Financial Period fields
- Quality Score: 95 (higher than Yahoo Finance 85)

**Verification:**
```bash
# Check downloaded filings
ls -la sites/yoursite.com/private/files/sec_edgar/sec-edgar-filings/{CIK}/

# Verify in Frappe console
import frappe
from cognitive_folio.utils.sec_edgar_fetcher import fetch_sec_edgar_financials
result = fetch_sec_edgar_financials('AAPL', '0000320193')
print(result)
```

**Note:** There is only one user action "Fetch Fundamentals". The app automatically tries SEC Edgar first for US companies, then falls back to Yahoo Finance.

### 3. Upload Financial Statements (PDF)

For companies not covered by SEC Edgar or Yahoo Finance:

1. Click **Actions → Upload Financial Statement**
2. Select the PDF file (10-Q, 10-K, annual report)
3. Choose period type (Annual/Quarterly)
4. System extracts and structures the data

### 4. Manual Data Entry

Create new **CF Financial Period** records directly:
- Link to security
- Set period type, fiscal year, quarter
- Fill in financial statement fields
- System auto-calculates metrics on save

**Pro Tip:** Use the "Copy from Previous Period" button to speed up entry.

### 5. View Reports

Access structured data through:
- **Financial Period Comparison Report** - Track trends over time with sparklines
- **Security Comparison Report** - Compare multiple companies side-by-side
- **Financial Metrics Dashboard** - Interactive charts and visualizations

### 6. AI Analysis

Financial data automatically enhances AI analysis:

**In CF Security AI Suggestions:**
```
Use {{periods:annual:5}} to include last 5 annual periods
Use {{periods:quarterly:4}} to include last 4 quarters
```

**In Chat Messages:**
```
Natural language: "compare Q3 vs Q2"
Auto-transforms to: {{periods:compare:2024Q3:2024Q2}}
```

**In Portfolio Analysis:**
```
Use ((periods:annual:3)) for portfolio-wide financial summary
Use ((periods:latest)) for most recent data across all holdings
```

---

## API & Developer Reference

### Query Financial Periods

```python
import frappe

# Get last 4 quarters for a security
periods = frappe.get_all(
    "CF Financial Period",
    filters={
        "security": "AAPL",
        "period_type": "Quarterly"
    },
    fields=[
        "fiscal_year", "fiscal_quarter", "period_end_date",
        "total_revenue", "net_income", "free_cash_flow",
        "gross_margin", "operating_margin", "net_margin",
        "roe", "roa", "debt_to_equity"
    ],
    order_by="period_end_date DESC",
    limit=4
)
```

### Import from Yahoo Finance

```python
from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import import_from_yahoo_finance

result = import_from_yahoo_finance(
    security_name="AAPL",
    replace_existing=False,  # Skip if better data exists
    respect_override=True    # Honor override_yahoo flag
)

# Returns: {
#   "success": True,
#   "imported": 5,
#   "updated": 3,
#   "skipped": 2,
#   "errors": []
# }
```

### Bulk Import

```python
from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import bulk_import_financial_periods

# Import for multiple securities
securities = ["AAPL", "MSFT", "GOOGL"]
result = bulk_import_financial_periods(
    security_names=securities,
    replace_existing=False,
    progress_id="bulk_import_123"  # For realtime progress tracking
)
```

### Format for AI

```python
from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import format_periods_for_ai

# Generate AI-ready summary
ai_context = format_periods_for_ai(
    security_name="AAPL",
    period_type="Annual",
    num_periods=5,
    include_growth=True,
    format="markdown"  # Options: markdown, text, json, table
)

# Use in AI prompt
prompt = f"Analyze the following financial data:\n\n{ai_context}"
```

### Data Freshness Tracking

```python
# Check data freshness
security = frappe.get_doc("CF Security", "AAPL")
security.update_data_freshness()

print(f"Last period: {security.last_financial_period_date}")
print(f"Days old: {security.days_since_last_period}")
print(f"Needs update: {security.needs_update}")  # True if >90 days (quarterly) or >365 days (annual)
```

### Valuation Using Structured Data

```python
# Valuation methods now use CF Financial Period queries
security = frappe.get_doc("CF Security", "AAPL")

# Fetch periods for analysis
periods = security._get_financial_periods(period_type="Annual", limit=5)

# DCF calculation uses structured data
dcf_value = security._calculate_dcf_value()  # Queries periods internally
residual_income = security._calculate_residual_income()
```

### Period Comparisons in Chat

Natural language comparison queries are automatically detected and transformed:

```python
# User input: "compare Q3 vs Q2"
# System transforms to: {{periods:compare:2024Q3:2024Q2}}

# Supported patterns:
# - "compare Q3 vs Q2"
# - "compare Q3 2024 vs Q2 2024"
# - "compare 2024 vs 2023"
# - "compare Q4 vs previous quarter"
# - "compare 2024 to previous year"
```

### Manual Period Entry Example

```python
# Create a new financial period
period = frappe.get_doc({
    "doctype": "CF Financial Period",
    "security": "PRIVATE_COMPANY",
    "period_type": "Annual",
    "fiscal_year": 2024,
    "period_end_date": "2024-12-31",
    "data_source": "Manual",
    "total_revenue": 1000000,
    "cost_of_revenue": 600000,
    "operating_expenses": 200000,
    "net_income": 150000,
    "total_assets": 2000000,
    "total_liabilities": 800000,
    "operating_cash_flow": 180000,
    "capital_expenditures": 50000
})

period.insert()
# System automatically calculates:
# - Gross profit (400,000)
# - Margins (40%, 20%, 15%)
# - Free cash flow (130,000)
# - Debt to equity ratio
# - ROE, ROA, etc.
```

### Best Practices

1. **Always use `format_periods_for_ai()`** for AI prompts - handles formatting and null values
2. **Query specific fields** instead of `fields=["*"]` for better performance
3. **Use `period_type` filter** to separate Annual, Quarterly, and TTM data
4. **Check `data_quality_score`** when comparing multiple sources
5. **Enable auto-import** in CF Settings for automatic Yahoo Finance imports

### Scheduled Tasks

The system includes automated maintenance:

```python
# Daily bulk import (configured in hooks.py)
# Runs for all securities with:
# - replace_existing=False (preserves better data)
# - respect_override=True (honors user locks)
```

---

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/cognitive_folio
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit

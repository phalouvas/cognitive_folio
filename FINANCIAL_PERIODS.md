# Structured Financial Data System

## Overview

The **CF Financial Period** DocType provides a structured, queryable database for storing financial statement data. This replaces the previous approach of storing large JSON blobs in text fields.

## Benefits

### 1. **Consistent Structure**
- Every company has data in the same format
- Same fields for all securities
- Easy to compare across companies

### 2. **Historical Tracking**
- Time series analysis built-in
- Automatic YoY growth calculations
- Track quarters and annual periods separately

### 3. **AI Efficiency**
- AI accesses clean, structured data instead of parsing PDFs
- Queries return only relevant periods
- Reduced token usage and faster responses

### 4. **Computed Metrics**
- Margins (Gross, Operating, Net) automatically calculated
- Financial ratios (ROE, ROA, Current Ratio, etc.) computed on save
- Growth metrics calculated when new periods added

### 5. **Data Validation**
- Field types enforce data quality
- Required fields ensure completeness
- Audit trail with track_changes enabled

## Structure

### Core Fields

**Period Identification:**
- `security` - Link to CF Security
- `period_type` - Annual, Quarterly, or TTM
- `fiscal_year` - Integer year (e.g., 2024)
- `fiscal_quarter` - Q1, Q2, Q3, Q4 (for quarterly only)
- `period_end_date` - Date when period ended
- `filing_date` - Date when filed with regulators
- `data_source` - Where data came from (Yahoo Finance, Manual, PDF, etc.)

**Income Statement:**
- Total Revenue, Cost of Revenue, Gross Profit
- Operating Expenses, Operating Income
- EBIT, EBITDA, Interest Expense
- Pretax Income, Tax Provision, Net Income
- Diluted EPS, Basic EPS

**Balance Sheet:**
- Total Assets, Current Assets, Cash and Equivalents
- Accounts Receivable, Inventory
- Total Liabilities, Current Liabilities
- Total Debt, Long Term Debt
- Shareholders Equity, Retained Earnings

**Cash Flow Statement:**
- Operating Cash Flow, Capital Expenditures
- Free Cash Flow, Investing Cash Flow
- Financing Cash Flow, Dividends Paid

**Computed Metrics (Auto-calculated):**
- Margins: Gross, Operating, Net
- Profitability: ROE, ROA
- Leverage: Debt to Equity
- Liquidity: Current Ratio, Quick Ratio
- Efficiency: Asset Turnover

**Growth Metrics (YoY):**
- Revenue Growth, Net Income Growth
- EPS Growth, FCF Growth
- Operating Cash Flow Growth

## Usage

### Import from Yahoo Finance

After fetching fundamentals from Yahoo Finance on a CF Security:

```python
# In Python
from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import import_from_yahoo_finance

result = import_from_yahoo_finance("AAPL")
# Returns: {"success": True, "imported_count": 12, "errors": []}
```

Or use the button in CF Security form: **Actions → Import to Financial Periods**

### Query Financial Data for AI

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
        "gross_margin", "net_margin", "roe"
    ],
    order_by="period_end_date DESC",
    limit=4
)

# Get annual data with growth metrics
annual_periods = frappe.get_all(
    "CF Financial Period",
    filters={
        "security": "AAPL",
        "period_type": "Annual"
    },
    fields=[
        "fiscal_year", "total_revenue", "net_income",
        "revenue_growth_yoy", "net_income_growth_yoy",
        "gross_margin", "operating_margin"
    ],
    order_by="fiscal_year DESC",
    limit=5
)
```

### Format for AI Prompt

```python
def format_periods_for_ai(security_name, num_periods=4):
    """Format financial periods for AI analysis"""
    periods = frappe.get_all(
        "CF Financial Period",
        filters={
            "security": security_name,
            "period_type": "Annual"
        },
        fields=["*"],
        order_by="fiscal_year DESC",
        limit=num_periods
    )
    
    prompt = f"Financial Data for {security_name}:\n\n"
    
    for period in periods:
        prompt += f"## Fiscal Year {period.fiscal_year} (ended {period.period_end_date})\n\n"
        prompt += f"**Income Statement:**\n"
        prompt += f"- Revenue: ${period.total_revenue:,.0f}\n"
        prompt += f"- Gross Profit: ${period.gross_profit:,.0f} ({period.gross_margin:.1f}% margin)\n"
        prompt += f"- Operating Income: ${period.operating_income:,.0f} ({period.operating_margin:.1f}% margin)\n"
        prompt += f"- Net Income: ${period.net_income:,.0f} ({period.net_margin:.1f}% margin)\n"
        prompt += f"- EPS: ${period.diluted_eps:.2f}\n\n"
        
        if period.revenue_growth_yoy:
            prompt += f"**Growth (YoY):**\n"
            prompt += f"- Revenue Growth: {period.revenue_growth_yoy:.1f}%\n"
            prompt += f"- Net Income Growth: {period.net_income_growth_yoy:.1f}%\n"
            prompt += f"- EPS Growth: {period.eps_growth_yoy:.1f}%\n\n"
        
        prompt += f"**Balance Sheet:**\n"
        prompt += f"- Total Assets: ${period.total_assets:,.0f}\n"
        prompt += f"- Total Debt: ${period.total_debt:,.0f}\n"
        prompt += f"- Shareholders Equity: ${period.shareholders_equity:,.0f}\n"
        prompt += f"- Debt/Equity: {period.debt_to_equity:.2f}\n\n"
        
        prompt += f"**Cash Flow:**\n"
        prompt += f"- Operating Cash Flow: ${period.operating_cash_flow:,.0f}\n"
        prompt += f"- Free Cash Flow: ${period.free_cash_flow:,.0f}\n"
        prompt += f"- FCF Margin: {(period.free_cash_flow/period.total_revenue*100):.1f}%\n\n"
        
        prompt += f"**Key Ratios:**\n"
        prompt += f"- ROE: {period.roe:.1f}%\n"
        prompt += f"- ROA: {period.roa:.1f}%\n"
        prompt += f"- Current Ratio: {period.current_ratio:.2f}\n"
        prompt += f"---\n\n"
    
    return prompt
```

### Compare with Previous Approach

**Before (JSON blobs):**
```python
# Stored as: {"2024-12-31T00:00:00.000": {"Total Revenue": 123456789, ...}}
# AI must parse entire JSON, find right date, extract values
# No history tracking, no automatic calculations
# Different field names across sources
```

**After (Structured periods):**
```python
# Stored as: Multiple CF Financial Period records
# AI queries exact fields needed
# Automatic growth calculations
# Consistent field names
# Easy to aggregate, compare, analyze
```

## Migration Path

1. **Keep existing JSON fields** - Don't delete them yet
2. **Import to structured format** - Use "Import to Financial Periods" button
3. **Update AI prompts** - Query CF Financial Period instead of parsing JSON
4. **Validate accuracy** - Compare structured vs JSON for few securities
5. **Gradually deprecate JSON** - Once confident, stop fetching to JSON blobs

## For AI Analysis

### Instead of uploading PDFs every time:

**Old workflow:**
1. User uploads Q3 2024 10-Q PDF
2. AI extracts revenue, expenses, etc. from PDF
3. AI analyzes based on extracted data
4. Data lost after chat ends

**New workflow:**
1. Data imported once to CF Financial Period (from Yahoo or PDF)
2. AI queries: "Get last 4 quarters for AAPL"
3. AI receives clean, structured data instantly
4. Historical data always available for trends

### AI Prompt Template Example

```
Analyze {{security}} based on the following structured financial data:

{{#financial_periods}}
Fiscal Year {{fiscal_year}} Q{{fiscal_quarter}}:
- Revenue: ${{total_revenue}} ({{revenue_growth_yoy}}% YoY growth)
- Net Income: ${{net_income}} ({{net_margin}}% margin)
- Free Cash Flow: ${{free_cash_flow}}
- ROE: {{roe}}%
- Debt/Equity: {{debt_to_equity}}
{{/financial_periods}}

Based on this data, evaluate:
1. Revenue growth trajectory
2. Profitability trends
3. Cash generation ability
4. Financial health
5. Valuation reasonableness
```

## Next Steps

1. **Create utility functions** - Helper functions to format periods for AI
2. **Update CF Chat Message** - Query CF Financial Period instead of JSON
3. **Add data entry UI** - Allow manual entry for non-Yahoo sources
4. **Build reports** - Financial statement reports, trend analysis
5. **Add PDF parsing** - Extract from 10-Q/10-K directly to CF Financial Period
6. **Peer comparison** - Compare multiple securities side-by-side

## Advanced Features (Future)

- **Automatic updates** - Monitor SEC Edgar for new filings
- **Data validation rules** - Ensure balance sheet balances
- **Segment reporting** - Store business segment breakdowns
- **Guidance tracking** - Store management guidance figures
- **Analyst estimates** - Compare actuals vs estimates
- **Non-GAAP metrics** - Store adjusted earnings, etc.

## Summary

The structured approach gives you:
- **Better data quality** - Validated, consistent format
- **Historical tracking** - Built-in time series
- **AI efficiency** - Clean queries, less token usage
- **Flexibility** - Accept data from any source (Yahoo, PDF, manual)
- **Scalability** - Easy to add more securities, more periods
- **Maintainability** - Clear structure, easy to debug

This is the **industry-standard approach** used by professional systems. You're moving from "unstructured documents" to "structured financial database" - a huge improvement! 🎯

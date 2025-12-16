# Financial Data Extraction and Standardization Prompt

## GOAL
Extract raw financial data from any source into a clean, standardized JSON format WITHOUT performing any calculations. Focus only on identifying available periods and extracting raw values.

## INPUT
Raw financial data from any source (SEC Edgar, yfinance, or company reports). The data may have different numbers of periods and different field names.

**Company:** {{security_name}} ({{symbol}})
**Sector:** {{sector}} | **Industry:** {{industry}}
**Current Price:** {{current_price}} {{currency}}

```json
{{financials:y10:q16}}
```

## OUTPUT
A **single JSON object** with this exact structure. All arrays should contain the available data in chronological order (most recent first). DO NOT calculate any ratios, margins, growth rates, or derived metrics.

```json
{
  "company_info": {
    "name": "{{security_name}}",
    "symbol": "{{symbol}}",
    "sector": "{{sector}}",
    "industry": "{{industry}}",
    "current_price": {{current_price}},
    "currency": "{{currency}}"
  },
  "data_quality": {
    "annual_periods_available": 6,
    "quarterly_periods_available": 4,
    "completeness": "High/Medium/Low",
    "notes": "Description of data quality and gaps"
  },
  "annual_data": {
    "years": [2023, 2022, 2021, 2020, 2019, 2018],
    "revenue": [1000, 900, 800, 700, 600, 500],
    "cost_of_goods_sold": [600, 540, 480, 420, 360, 300],
    "gross_profit": [400, 360, 320, 280, 240, 200],
    "operating_income": [200, 180, 160, 140, 120, 100],
    "ebit": [200, 180, 160, 140, 120, 100],
    "interest_expense": [10, 9, 8, 7, 6, 5],
    "net_income": [150, 135, 120, 105, 90, 75],
    "operating_cash_flow": [180, 162, 144, 126, 108, 90],
    "capital_expenditures": [30, 27, 24, 21, 18, 15],
    "total_assets": [2000, 1800, 1600, 1400, 1200, 1000],
    "current_assets": [800, 720, 640, 560, 480, 400],
    "inventory": [200, 180, 160, 140, 120, 100],
    "accounts_receivable": [150, 135, 120, 105, 90, 75],
    "current_liabilities": [400, 360, 320, 280, 240, 200],
    "total_debt": [500, 450, 400, 350, 300, 250],
    "shareholders_equity": [1000, 900, 800, 700, 600, 500],
    "shares_outstanding": [100, 100, 100, 100, 100, 100]
  },
  "quarterly_data": {
    "periods": ["Q1 2024", "Q4 2023", "Q3 2023", "Q2 2023"],
    "revenue": [250, 225, 200, 175],
    "net_income": [38, 34, 30, 26]
  }
}
```

## EXTRACTION RULES
### 1. Handle Different Data Lengths:
- **Annual Data**: Extract ALL available years (minimum 1 year)
- **Quarterly Data**: Extract ALL available quarters (can be 0, 4, 8, 12, 16, etc.)
- **Array Order**: Most recent period FIRST (2023, 2022, 2021...)
- **Missing Data**: Use `null` for unavailable metrics in otherwise available periods

### 2. Field Name Mapping:
Map common alternative names to these standard names:
- Revenue: "Revenue", "Total Revenue", "Sales", "Turnover"
- Cost of Goods Sold: "CostOfGoodsSold", "COGS", "Cost of Sales"
- Gross Profit: "GrossProfit", "Gross Margin"
- Operating Income: "OperatingIncome", "Operating Profit", "EBIT"
- EBIT: "EBIT", "Earnings Before Interest and Tax", "Operating Income"
- Interest Expense: "InterestExpense", "Interest Paid", "Finance Costs"
- Net Income: "NetIncome", "Net Profit", "Profit After Tax"
- Operating Cash Flow: "OperatingCashFlow", "Cash from Operations"
- Capital Expenditures: "CapitalExpenditures", "CAPEX", "Purchase of PPE"
- Total Assets: "TotalAssets", "Assets"
- Current Assets: "CurrentAssets", "Short-term Assets"
- Inventory: "Inventory", "Inventories", "Stock"
- Accounts Receivable: "AccountsReceivable", "Receivables", "Trade Receivables"
- Current Liabilities: "CurrentLiabilities", "Short-term Liabilities"
- Total Debt: "TotalDebt", "Long Term Debt", "Total Liabilities"
- Shareholders Equity: "ShareholdersEquity", "Total Equity", "Stockholders Equity"
- Shares Outstanding: "SharesOutstanding", "Common Stock Outstanding"

### 3. Data Quality Assessment:
- Count available annual periods
- Count available quarterly periods
- Check for critical fields in each period
- Note any gaps in the time series
- Assess completeness based on percentage of expected fields present:
  - High: >80% of expected fields present
  - Medium: 50-80% of expected fields present  
  - Low: <50% of expected fields present

## INSTRUCTIONS
1. **Identify Available Periods**:
   - List all available years for annual data
   - List all available quarters for quarterly data
   - Note if periods are consecutive or have gaps

2. **Extract Raw Values Only**:
   - For each year, extract all available metrics as raw numbers
   - For each quarter, extract revenue and net income as raw numbers
   - Use `null` for missing metrics in otherwise available periods
   - DO NOT calculate derived values (gross profit, margins, ratios, etc.)

3. **Standardize Format**:
   - Ensure all arrays have the same length as the years/periods array
   - Use consistent field names as specified
   - Convert all values to numbers (integers or floats)

4. **Output ONLY the JSON object**, no additional text or calculations.

## IMPORTANT
- **Extract only**: Do not perform any calculations
- **Be consistent**: Always use same order (most recent first)
- **Handle missing**: Use `null` for unavailable data, not zero
- **Preserve precision**: Keep original numerical precision
- **No transformations**: Output raw extracted values exactly as found
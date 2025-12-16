# Investment Analysis Prompt Template

**NOTE**: This file is for documentation and git history purposes only. At runtime, the system uses database-stored prompts from the `CF Prompt` doctype via the `template_prompt` field. This document serves as a reference for the expected prompt structure and AI response format.

---

## Purpose

Generate deterministic investment analysis using pre-calculated financial ratios and company fundamentals. The AI interprets the quantitative data to provide qualitative assessment and investment recommendations.

## Input Data Structure

The prompt should include access to the following variables (via template replacement):

### Company Information
- `{{security_name}}` - Company name
- `{{symbol}}` - Stock ticker symbol
- `{{sector}}` - Business sector
- `{{industry}}` - Industry classification
- `{{country}}`, `{{region}}`, `{{subregion}}` - Geographic classification
- `{{current_price}}` - Current stock price
- `{{currency}}` - Currency denomination

### Code-Calculated Valuation (Reference Only)
- `{{intrinsic_value}}` - True fundamental worth based on DCF/DDM/Graham models
- `{{fair_value}}` - Market-adjusted value (authoritative code calculation)

### Financial Ratios (Pre-Calculated)
- `{{financial_ratios}}` - Complete ratio analysis including:
  - **Liquidity**: current_ratio, quick_ratio, working_capital, working_capital_ratio
  - **Profitability**: net_profit_margin, gross_profit_margin, operating_margin, ROA, ROE, ROIC
  - **Efficiency**: asset_turnover, receivables_days
  - **Growth**: revenue_growth_5y, earnings_growth_5y, eps_growth_5y
  - **Valuation**: pe_ratio, pb_ratio, dividend_yield, payout_ratio
  - **Debt Health**: debt_to_equity, debt_to_assets, interest_coverage, free_cash_flow
  - **Quality**: earnings_stability, fcf_conversion, revenue_consistency
  - **Data Quality**: annual_periods, quarterly_periods, coverage (High/Medium/Low)

### Raw Financial Data
- `{{fetched_data}}` - Complete extracted financial statements (annual/quarterly)
- `{{ticker_info}}` - Company metadata from Yahoo Finance
- `{{profit_loss}}`, `{{balance_sheet}}`, `{{cash_flow}}` - Financial statements
- `{{dividends}}` - Dividend payment history
- `{{news}}`, `{{news_urls}}` - Recent news and sentiment

---

## Expected Output Format

The AI must return **valid JSON only** with the following structure:

```json
{
    "Evaluation": {
        "Moat": <integer 1-10>,
        "Management": <integer 1-10>,
        "Financials": <integer 1-10>,
        "Valuation": <integer 1-10>,
        "Industry": <integer 1-10>,
        "Overall": <integer 1-10>
    },
    "Investment": {
        "Action": "Buy|Hold|Sell",
        "Conviction": "High|Medium|Low",
        "FairValue": <number or null>,
        "BuyBelowPrice": <number or null>,
        "SellAbovePrice": <number or null>,
        "StopLoss": <number or null>
    },
    "Summary": "2-3 sentence concise summary",
    "Risks": ["Risk 1", "Risk 2", "Risk 3"],
    "Analysis": "Detailed analysis with reasoning based on ratios and data"
}
```

### Field Mappings to CF Security Doctype

| AI Response Field | CF Security Field | Type | Notes |
|-------------------|-------------------|------|-------|
| `Evaluation.Moat` | `rating_moat` | Rating (1-10) | Competitive advantages |
| `Evaluation.Management` | `rating_management` | Rating (1-10) | Leadership quality |
| `Evaluation.Financials` | `rating_financials` | Rating (1-10) | **Use ratios to justify** |
| `Evaluation.Valuation` | `rating_valuation` | Rating (1-10) | Fair value assessment |
| `Evaluation.Industry` | `rating_industry` | Rating (1-10) | Industry trends |
| Average of all 5 ratings | `suggestion_rating` | Rating (1-10) | Composite score |
| `Investment.Action` | `suggestion_action` | Select | Buy/Hold/Sell |
| `Investment.FairValue` | `suggestion_fair_value` | Currency | **AI-calculated fair value** |
| `Investment.BuyBelowPrice` | `suggestion_buy_price` | Currency | Entry price target |
| `Investment.SellAbovePrice` | `suggestion_sell_price` | Currency | Exit price target |
| `Investment.StopLoss` | `evaluation_stop_loss` | Currency | Risk management level |
| Full JSON | `ai_response` | JSON | Raw response for audit |
| Markdown conversion | `ai_suggestion` | Markdown | Display version |

---

## Critical Rules for AI Analysis

### 1. Rating Requirements
- All ratings MUST be integers from 1 to 10 (no decimals, no 0)
- Use the pre-calculated ratios to justify `Financials` and `Valuation` ratings
- Consider data quality coverage (High/Medium/Low) in confidence level

### 2. Price Target Calculation
The AI should:
- Calculate `FairValue` based on:
  - Financial ratios (profitability, growth, debt health)
  - Code-calculated `fair_value` as reference (but not required to match exactly)
  - Industry comparables (P/E, P/B ratios)
  - Qualitative factors (moat, management, industry trends)
- Derive `BuyBelowPrice` using risk-based margin of safety:
  - Low risk (high quality ratios): 10-15% below fair value
  - Medium risk: 20-25% below fair value
  - High risk (weak ratios): 30-40% below fair value
- Derive `SellAbovePrice` using profit targets:
  - Low risk: 15-20% above fair value
  - Medium risk: 25-30% above fair value
  - High risk: 40-50% above fair value
- Calculate `StopLoss`:
  - Low risk: 8-10% below fair value
  - Medium risk: 12-15% below fair value
  - High risk: 18-25% below fair value

### 3. Action Determination
- **Buy**: If `current_price <= BuyBelowPrice`
- **Sell**: If `current_price >= SellAbovePrice`
- **Hold**: Otherwise

### 4. Data Quality Warnings
If `data_quality.coverage` is "Low" or "Medium":
- Include warning in `Analysis` section
- Explain data limitations
- Reduce conviction level
- Widen margin of safety

Example:
```
⚠️ Data Quality: Medium coverage (3 years annual, 8 quarters). Analysis confidence is moderate due to limited historical data.
```

### 5. Ratio-Based Reasoning
The AI MUST reference specific ratios when justifying ratings:
- **Financials rating**: Cite profitability margins, ROE, ROA, debt ratios
- **Valuation rating**: Reference P/E, P/B relative to industry, growth rates
- **Example**: "Financials: 8/10 - Strong ROE of 18%, healthy debt-to-equity of 0.4, but declining operating margin (12% → 9%) is concerning."

---

## Model Configuration

- **Model**: `deepseek-chat` (hardcoded for consistency)
- **Temperature**: `0.1` (low variance for deterministic output)
- **Top-p**: `0.95`
- **JSON Mode**: Enabled
- **Presence Penalty**: `0.0`
- **Frequency Penalty**: `0.0`

---

## Example Prompt Template (Database-Stored)

```markdown
You are an investment analyst. Analyze the following security and provide investment recommendations in valid JSON format.

## Security Information
- **Company**: {{security_name}} ({{symbol}})
- **Sector**: {{sector}} | **Industry**: {{industry}}
- **Location**: {{country}}, {{region}}
- **Current Price**: {{currency}} {{current_price}}

## Code-Calculated Valuations (Reference)
- **Intrinsic Value**: {{currency}} {{intrinsic_value}}
- **Fair Value**: {{currency}} {{fair_value}}

## Financial Ratios (Pre-Calculated)
{{financial_ratios}}

## Data Quality
{{data_quality}}

## Recent News
{{news}}

## Instructions
1. Evaluate the company on 5 dimensions (Moat, Management, Financials, Valuation, Industry) - integers 1-10 only
2. Use the financial ratios to justify your Financials and Valuation ratings
3. Calculate your own fair value estimate and price targets (BuyBelowPrice, SellAbovePrice, StopLoss)
4. Include data quality warnings in your Analysis if coverage is Low/Medium
5. Return ONLY valid JSON (no markdown, no commentary)

**Output Format:**
{
    "Evaluation": {
        "Moat": <1-10>,
        "Management": <1-10>,
        "Financials": <1-10>,
        "Valuation": <1-10>,
        "Industry": <1-10>,
        "Overall": <1-10>
    },
    "Investment": {
        "Action": "Buy|Hold|Sell",
        "Conviction": "High|Medium|Low",
        "FairValue": <number>,
        "BuyBelowPrice": <number>,
        "SellAbovePrice": <number>,
        "StopLoss": <number>
    },
    "Summary": "...",
    "Risks": ["...", "..."],
    "Analysis": "..."
}
```

---

## Notes

- **Fair Value Authority**: The code-calculated `fair_value` is authoritative for system consistency. AI's `suggestion_fair_value` provides qualitative confirmation.
- **Backward Compatibility**: Existing templates using old response format are supported via parsing logic in `process_security_ai_suggestion()`.
- **Template Customization**: Users can edit prompts via CF Prompt doctype for specific analysis needs.
- **Git History**: This file tracks prompt evolution and serves as reference documentation.

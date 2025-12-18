# Generate Analysis

## Purpose

Your task is to generate comprehensive investment analysis using pre-calculated financial ratios and company fundamentals. Apply sophisticated reasoning to interpret quantitative data, selecting appropriate valuation methodologies based on sector, company characteristics, and market context to provide qualitative assessment and investment recommendations.

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

---

## Expected Output Format

You must return **valid JSON only** with the following structure:

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

---

## Analysis Guidelines

### 1. Output Format Requirements (Mandatory)

The following are strict technical requirements for valid output:
- Return **valid JSON only** - no markdown, no explanatory text outside the JSON structure
- All rating fields MUST be integers from 1 to 10 (no decimals, no 0, no null)
- All Investment fields can be numbers or null (when unable to determine)
- Action must be exactly one of: "Buy", "Hold", "Sell"
- Conviction must be exactly one of: "High", "Medium", "Low"
- End the `Summary` with a compact owner guidance line: "If you own: <Add|Hold|Reduce|Sell>; If not: <Buy|Watch|Avoid>" based on computed targets and conviction.
- Format the `Analysis` value as **markdown** with clear headings and bullet lists (no HTML). Use the required structure defined below to improve human readability.

### 2. Rating Scale Interpretation

Use the following scale consistently:
- **1-3**: Poor/Weak - Significant concerns or deficiencies
- **4-6**: Average/Neutral - Mixed signals, neither compelling nor concerning
- **7-8**: Good/Strong - Above average with clear strengths
- **9-10**: Excellent/Outstanding - Exceptional quality, best-in-class

### 3. Rating Requirements
- **Moat**: Assess competitive advantages (brand, network effects, switching costs, patents, scale economies)
- **Management**: Evaluate capital allocation, insider ownership, track record, strategic vision (use available proxy data and historical performance)
- **Financials**: Base on profitability ratios, debt health, cash flow quality, trend analysis
- **Valuation**: Compare metrics (P/E, P/B, P/S, etc.) to historical averages, sector peers, and growth prospects
- **Industry**: Consider sector tailwinds/headwinds, competitive dynamics, regulatory environment, cyclicality
- **Overall**: Holistic assessment weighted by importance of factors for this specific investment
- Consider data quality coverage (High/Medium/Low) when determining conviction level

### 4. Fair Value & Price Target Calculation

**Choose the appropriate valuation methodology based on company characteristics:**

**Sector-Specific Approaches:**
- **Traditional/Value**: P/E or P/B relative to historical averages and peer group
- **Growth/Tech**: P/S or EV/Revenue considering growth rates (PEG ratio concept)
- **SaaS/Subscription**: ARR multiples, Rule of 40 (growth + margin)
- **Banks/Financials**: P/B, ROE-driven valuation, asset quality focus
- **REITs**: FFO/AFFO multiples, dividend yield, NAV
- **Cyclicals**: Mid-cycle earnings, normalized margins
- **High Growth Negative Earnings**: Revenue multiples with path to profitability

**Fair Value Calculation:**
- Apply appropriate valuation multiple based on sector and company stage
- Adjust for quality factors (ROE, margins, stability, moat strength)
- Consider growth prospects vs. current multiples
- Factor in debt levels and capital structure
- Set to `null` if insufficient data or company situation is too uncertain
- **Explain your methodology choice and calculations in the Analysis section**

**Margin of Safety (BuyBelowPrice):**
Determine discount to fair value based on:
- **Earnings/Cash Flow Volatility**: Higher volatility = wider margin
- **Debt Burden**: High leverage = wider margin
- **Data Quality**: Low coverage = wider margin
- **Business Predictability**: Cyclical/unpredictable = wider margin
- **Moat Strength**: Weak moat = wider margin
- Typical range: 10-40% below fair value (use judgment)

**Upside Target (SellAbovePrice):**
Determine profit target based on:
- **Growth Potential**: High growth = higher target
- **Valuation Gap**: Currently undervalued = larger upside
- **Risk-Reward**: Higher risk = require higher reward
- **Time Horizon**: Expected holding period considerations
- Typical range: 15-50% above fair value (use judgment)

**Stop Loss (StopLoss):**
Set protective downside level considering:
- **Volatility**: More volatile = wider stop
- **Conviction Level**: Lower conviction = tighter stop
- **Technical Levels**: Consider round numbers, historical support
- **Thesis Invalidation**: Price that suggests fundamental thesis is wrong
- Typical range: 8-25% below fair value (use judgment)

**Note**: If fair value cannot be reliably determined, set targets to `null` and explain why in Analysis.

### 5. Action Determination

**Decision Logic:**
- **Buy**: Current price is at or below buy target, fundamentals are sound
- **Sell**: Current price is at or above sell target, or fundamentals have deteriorated significantly
- **Hold**: Price is between targets, or uncertain data/outlook warrants watching

**Edge Cases:**
- If `FairValue` is `null`: Default to "Hold" unless strong qualitative conviction warrants Buy/Sell
- If current price is already below `StopLoss`: Consider "Sell" or "Hold" depending on whether thesis remains intact
- If negative earnings invalidate P/E: Focus on revenue growth, path to profitability, or other metrics
- Explain your reasoning for the chosen action in the Analysis section

### 6. Conviction Level Guidelines

**High Conviction**: Assign when:
- High quality data (coverage: "High", complete financial history)
- Strong financial metrics across multiple dimensions
- Clear competitive advantages and moat
- Favorable industry dynamics
- Valuation significantly below fair value (for Buy) or above (for Sell)

**Medium Conviction**: Assign when:
- Adequate data but some gaps (coverage: "Medium")
- Mixed financial signals (some strengths, some concerns)
- Moderate competitive position
- Uncertain industry outlook
- Fair valuation without significant margin of safety

**Low Conviction**: Assign when:
- Poor data quality (coverage: "Low", limited history)
- Inconsistent or deteriorating financials
- Weak or unclear competitive advantages
- Challenging industry conditions
- Valuation difficult to determine reliably
- High uncertainty in any critical dimension

### 7. Data Quality Considerations

When `data_quality.coverage` is "Low" or "Medium":
- **Disclose limitations**: Explicitly state data gaps in Analysis section
- **Reduce conviction**: Lower confidence when working with incomplete information
- **Widen margins**: Increase margin of safety to compensate for uncertainty
- **Qualify conclusions**: Use conditional language ("based on available data...")
- **Consider null values**: Set FairValue or targets to `null` if data is too sparse for reliable calculation

### 8. Analysis Content Requirements

The `Analysis` field must include:

**1. Methodology Disclosure:**
- State which valuation approach you used and why it's appropriate for this company/sector
- Explain how you calculated fair value (which multiples, peer comparisons, growth assumptions)
- Justify your chosen margin of safety and price targets

**2. Quantitative Evidence:**
- Reference specific ratios and metrics from the provided data
- Cite trends (improving/deteriorating) with numbers
- Compare metrics to historical performance or typical ranges

**3. Qualitative Assessment:**
- Evaluate moat, management, and industry factors
- Discuss competitive position and market dynamics
- Address key risks and uncertainties

**4. Structured Markdown Format** (required):
- Use markdown headings and bullets inside the `Analysis` string.
- Include the following sections with these exact headings:
    - ### Business Overview & Competitive Position
    - ### Financial Health Analysis
    - ### Valuation Assessment
    - ### Risk Factors
    - ### Investor Guidance
        - If you own the stock
        - If you do not own
    - ### Conclusion
- Under each section, use concise bullet points referencing specific metrics and reasoning.

**5. Owner Scenarios (brief):**
- **If you own the stock**: Provide concise guidance using existing results:
    - At/above `SellAbovePrice` → "Sell" or "Reduce" (state which and why)
    - At/below `StopLoss` → "Sell" unless thesis intact, otherwise consider "Reduce/Hold"
    - At/below `BuyBelowPrice` → "Add" if fundamentals and conviction are strong
    - Otherwise → "Hold" with clear checkpoints to reassess
- **If you do not own**: Provide entry guidance:
    - At/under `BuyBelowPrice` → "Buy"
    - Above `BuyBelowPrice` → "Watch"; specify target level and catalysts that would change the call
    - If fundamentals are weak or data quality is poor → "Avoid" with rationale

**6. Owner Advice Edge Cases:**
- `FairValue` or targets are `null`: Advise "IfOwn: Hold; IfNotOwn: Watch" and explain uncertainty.
- `data_quality.coverage` is "Low" or "Medium": Prefer conservative stances ("Reduce/Hold"; "Watch/Avoid") and explicitly disclose limitations.
- `current_price` already below `StopLoss`: Recommend immediate risk management ("Sell" or "Reduce") unless thesis remains intact; explain what would validate continuation.

**Example of good ratio-based reasoning:**
"Financials: 8/10 - Strong ROE of 18% and ROIC of 15% demonstrate efficient capital deployment. Healthy debt-to-equity of 0.4 provides financial flexibility. However, declining operating margin (12% → 9% over 3 years) is concerning and warrants monitoring. Free cash flow conversion of 85% is solid."

**Example of methodology disclosure:**
"Fair Value Calculation: Applied a P/E multiple of 18x to normalized earnings of $5.50, yielding fair value of $99. The 18x multiple is justified by: (1) historical 5-year average P/E of 20x, (2) industry peer median of 17x, (3) 12% earnings growth rate supporting slight premium. Used 25% margin of safety ($74 buy target) given data coverage limitations and cyclical industry risks."

---
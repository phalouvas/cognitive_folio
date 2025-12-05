# Security Evaluation - JSON Auto-Update Format

## Security Overview
**Company:** {{security_name}} ({{symbol}})  
**Sector:** {{sector}}  
**Industry:** {{industry}}  
**Market Cap:** {{ticker_info.marketCap}}  
**Current Price:** {{current_price}} {{currency}}

---

## Financial Statements (10 years annual, 16 quarters)
{{financials:y10:q16}}

---

## Valuation Metrics
- **Trailing P/E:** {{ticker_info.trailingPE}}
- **Forward P/E:** {{ticker_info.forwardPE}}
- **Price to Book:** {{ticker_info.priceToBook}}
- **Price to Sales:** {{ticker_info.priceToSales}}
- **Enterprise Value:** {{ticker_info.enterpriseValue}}
- **EV/Revenue:** {{ticker_info.enterpriseToRevenue}}
- **EV/EBITDA:** {{ticker_info.enterpriseToEbitda}}
- **PEG Ratio:** {{ticker_info.pegRatio}}
- **Beta:** {{ticker_info.beta}}
- **Book Value:** {{ticker_info.bookValue}}

---

## Dividend & Shareholder Returns
- **Dividend Yield:** {{ticker_info.dividendYield}}
- **Dividend Rate:** {{ticker_info.dividendRate}}
- **Payout Ratio:** {{ticker_info.payoutRatio}}
- **5-Year Avg Dividend Yield:** {{ticker_info.fiveYearAvgDividendYield}}
- **Trailing Annual Dividend Rate:** {{ticker_info.trailingAnnualDividendRate}}
- **Trailing Annual Dividend Yield:** {{ticker_info.trailingAnnualDividendYield}}

---

## Data Reliability Assessment

**BEFORE ANALYSIS**: Assess the quality and completeness of provided financial data:

1. **Critical Fields Check**: Are these populated across most periods?
   - Income Statement: total_revenue, net_income, operating_income, gross_profit
   - Balance Sheet: total_assets, total_liabilities, shareholders_equity, current_assets, current_liabilities
   - Cash Flow: operating_cash_flow, free_cash_flow, capital_expenditures
   - Valuation: trailing P/E, forward P/E, current price
   
2. **Inconsistency Detection**: Look for red flags:
   - Revenue declining sharply but margins expanding unexpectedly (possible data error)
   - P/E ratios extreme or missing (possible data quality issue)
   - Historical trend broken or gaps in periods (incomplete history)
   
3. **History Sufficiency**:
   - Annual periods <3: **Low reliability** (insufficient trend data)
   - Annual periods 3-5: **Medium reliability** (limited history, but workable)
   - Annual periods 6+: **High reliability** (sufficient for trends)
   - Quarterly periods <4: **Low reliability** (insufficient recent trend)
   - Quarterly periods 4+: **Good reliability** (recent trends visible)

**Data Reliability Rating**: After assessment, state:
- **High**: All critical fields >80% populated, no inconsistencies, 6+ annual periods available → Proceed with full confidence
- **Medium**: 60-80% of critical fields populated, minor gaps, 3-5 annual periods → Proceed but note limitations
- **Low**: <60% of critical fields populated, inconsistencies present, <3 annual periods → Flag issues clearly; proceed with heavy caveats and note this is preliminary analysis pending complete data

**If data reliability is Low or Medium, explicitly state limitations in your Summary and acknowledge how this affects rating confidence.**

---

## Quantitative Anchoring Rules

**CRITICAL**: Your ratings and price targets MUST be justified using the specific numbers provided above. You cannot make claims without data evidence.

### Rating Guidelines (1-10 Integer Scale)

**These guidelines are suggestive anchors based on common patterns. Adjust ratings for sector context and competitive positioning using your judgment.**

**Moat (Competitive Advantage)** - Base on MEASURABLE indicators:
- **8-10**: Typically associated with gross margin >50% AND stable/growing over 5 years, ROE >20%, demonstrated pricing power. (Adjust for sector: tech software 60%+ is normal; industrials 35%+ is strong)
- **5-7**: Typically associated with gross margin 30-50%, ROE 10-20%, some competitive advantages visible in financials. (Adjust for sector norms)
- **1-4**: Typically associated with gross margin <30% OR declining margins over time, ROE <10%, commoditized business
- **REQUIRED**: Cite specific gross margin trend from periods data and ROE from financials. Use your reasoning to justify the final score based on sector context and financial evidence.

**Management (Capital Allocation)** - Base on OBSERVABLE decisions:
- **8-10**: Typically strong FCF generation (>90% of net income), prudent leverage (D/E <0.5), consistent shareholder returns. (Adjust based on capital intensity of sector)
- **5-7**: Typically moderate FCF (60-90% of net income), reasonable leverage (D/E 0.5-1.5), mixed capital decisions
- **1-4**: Typically weak/negative FCF, high leverage (D/E >2.0), poor capital allocation track record
- **REQUIRED**: Reference cash flow from operations, debt levels, and dividend/buyback data from financials. Justify your score using reasoning aligned with sector capital requirements.

**Financials (Health & Profitability)** - Base on ACTUAL metrics:
- **8-10**: Typically revenue growth >15% YoY, net margin >15%, strong liquidity (current ratio >2.0), ROE >20%. (Adjust for cyclical sectors and growth phase)
- **5-7**: Typically revenue growth 5-15%, net margin 5-15%, adequate liquidity (current ratio 1.0-2.0), ROE 10-20%
- **1-4**: Typically revenue decline or <5% growth, net margin <5%, liquidity concerns (current ratio <1.0), ROE <10%
- **REQUIRED**: State exact revenue growth rate, net margin, and liquidity ratios from the data above. Use your judgment to rate within this range based on sector context.

**Valuation (Attractiveness)** - Base on CALCULATED fair value:
- **8-10**: Typically trading below fair value with >15% margin of safety, P/E <15 with growth >10%, or PEG <1.0
- **5-7**: Typically trading near fair value, P/E 15-25 with moderate growth, PEG 1.0-2.0
- **1-4**: Typically trading above fair value, P/E >30 with low growth, PEG >2.5
- **REQUIRED**: Use trailing P/E and/or forward P/E from ticker_info, calculate PEG ratio explicitly. Justify your fair value calculation.

**Industry (Competitive Position)** - Base on RELATIVE performance:
- **8-10**: Typically growing faster than industry average (if known), margins above sector median, market leadership evidence
- **5-7**: Typically in-line with industry growth, margins near sector average, solid market position
- **1-4**: Typically underperforming industry growth, margins below average, losing competitive position
- **REQUIRED**: If industry data unavailable, compare to own historical growth rates and acknowledge limitation. Justify competitive position based on financial evidence.

### Price Target Calculation - MANDATORY METHODOLOGY

You MUST show your calculation using one of these methods:

**Method 1: P/E Multiple Approach** (Preferred for profitable companies)
```
Step 1: Determine Fair Value P/E
- Trailing P/E: [from ticker_info.trailingPE]
- Forward P/E: [from ticker_info.forwardPE if available]
- Justification for target P/E: [explain based on growth rate, sector, and trailing/forward P/E comparison]

Step 2: Project Target EPS
- Latest annual EPS: [get from latest annual period]
- Expected EPS growth rate: [justify from historical trend]
- Target EPS = Latest EPS × (1 + growth rate)

Step 3: Calculate Fair Value
- Fair Value = Target P/E × Target EPS
- Show calculation: [number] × [number] = $[result]

Step 4: Set Trading Targets
- Buy Below: Fair Value × 0.80 (20% margin of safety)
- Sell Above: Fair Value × 1.20 (20% upside target)
- Stop Loss: Buy Price × 0.75 (25% maximum loss)
```

**Method 2: Price/Sales Approach** (For high-growth, low-margin companies)
```
Step 1: Calculate Revenue Per Share
- Latest revenue: [from data]
- Shares outstanding: [calculate from market cap / price]
- Revenue per share = Revenue / Shares

Step 2: Determine Target P/S Ratio
- Historical P/S: [from Price to Sales metric]
- Industry average P/S: [if available, else use historical]
- Target P/S: [justify choice]

Step 3: Calculate Fair Value
- Fair Value = Target P/S × Revenue per share × (1 + revenue growth rate)
- Show calculation

Step 4: Set Trading Targets (same as Method 1)
```

**Method 3: EV/EBITDA Approach** (For capital-intensive businesses)
```
Use EV/EBITDA, EV/Revenue ratios from provided data
Compare to historical averages
Calculate implied equity value and price per share
```

### Prohibited Behaviors - STRICT ENFORCEMENT

- ❌ **NO invented metrics**: Don't cite "strong competitive moat" without margin/ROE data
- ❌ **NO vague valuations**: Don't say "reasonably valued" without showing P/E comparison
- ❌ **NO unexplained ratings**: Every rating 1-10 must cite specific numbers
- ❌ **NO price targets without math**: Must show step-by-step calculation
- ❌ **NO ignoring negative data**: Declining margins, rising debt must be addressed
- ❌ **NO assumptions about missing data**: If data is incomplete, state it explicitly

### Data Quality Requirements

**You MUST acknowledge in your Summary if:**
- Historical data is incomplete (e.g., "Only 3 annual periods available instead of 5")
- Key metrics are missing (e.g., "P/E ratio not available, using P/S instead")
- Recent periods show data quality issues (e.g., "Latest quarter shows unusual items")
- Comparisons are limited (e.g., "No industry benchmarks available")

---

## Analysis Instructions

**REASONING APPROACH**: You have extended reasoning capability (deepseek_reasoner). When assigning ratings, show your thinking chain:
- Why does this specific metric warrant this score?
- What sector context applies? (Tech software requires different thresholds than industrials)
- Does this evidence support the score, or does competitive context suggest adjustment?
- Don't force data into preset bands—use judgment informed by financial evidence and sector norms.

Analyze this security considering **sector-specific factors**:

### Sector-Specific Focus Areas:
- **Financials (Banks, Insurance, REITs):** Emphasize book value, capital ratios (Tier 1 for banks), loan quality metrics (NPL ratios), dividend sustainability, regulatory compliance, interest rate sensitivity
- **Technology:** Prioritize revenue growth rates, R&D efficiency (R&D as % of revenue), gross margins (should be >60% for software), customer acquisition costs vs lifetime value, platform effects, competitive moat from network effects
- **Industrials:** Assess asset turnover ratios, working capital management, order backlog strength, cyclical positioning, operating leverage, capacity utilization
- **Consumer (Retail/CPG):** Evaluate brand strength, same-store sales growth, inventory turnover, gross margin sustainability, pricing power, customer retention
- **Healthcare (Pharma/Biotech):** Consider regulatory approval risks, pipeline strength and stage, patent cliff exposure, reimbursement trends, R&D productivity

---

## Required JSON Response Format

**IMPORTANT:** Your response MUST be valid JSON with the following structure:

```json
{
  "Summary": "A concise executive summary (100-150 words). MUST include: (1) Data quality note if incomplete, (2) Investment thesis in 2-3 sentences citing specific metrics, (3) Key decision factors with numbers, (4) Most critical risk to monitor.",
  "Evaluation": {
    "Rating": {
      "Moat": 7,
      "Management": 8,
      "Financials": 7,
      "Valuation": 6,
      "Industry": 8
    },
    "Rating_Justification": {
      "Moat": "Gross margin expanded from 38% to 43% over 5 years (see annual data), ROE consistently above 23%. Demonstrates pricing power. Rated 7/10.",
      "Management": "FCF conversion at 95% of net income, debt-to-equity reduced from 0.5 to 0.3, consistent dividend growth of 8% annually. Rated 8/10.",
      "Financials": "Revenue growth 18% YoY (from period comparison), net margin 12% (vs 10% prior year), current ratio 2.1 shows strong liquidity. Rated 7/10.",
      "Valuation": "Trailing P/E 24 vs Forward P/E 21 (moderate premium to forward). PEG ratio 1.8 (24 P/E / 13% growth). Moderately overvalued. Rated 6/10.",
      "Industry": "Market leader with stable competitive position. Revenue growth outpaces historical average. Rated 8/10."
    },
    "Price_Target_Calculation": {
      "Method": "P/E Multiple Approach",
      "Current_Price": 145.50,
      "Trailing_PE": 24.0,
      "Forward_PE": 21.0,
      "Target_PE": 22,
      "Target_PE_Justification": "Between trailing (24) and forward (21) P/E, using 22 based on 13% growth rate and sector average",
      "Latest_EPS": 6.10,
      "Expected_Growth_Rate": 0.13,
      "Target_EPS": 6.89,
      "Calculation": "Fair P/E 22 × Target EPS $6.89 (current $6.10 × 1.13 growth) = $151.58 fair value",
      "Fair_Value": 151.58
    },
    "Recommendation": "Buy",
    "Price Target Buy Below": 130.00,
    "Price Target Sell Above": 175.00,
    "Price Stop Loss": 110.00,
    "Price_Target_Rationale": "Buy Below at $130 provides 14% margin of safety from $151.58 fair value. Sell Above at $175 represents 16% upside (P/E of 25). Stop Loss at $110 limits downside to 15% from buy price."
  },
  "Analysis": "Detailed analysis text here covering all aspects...",
  "Risks": "Key risks text here..."
}
```

### JSON Field Specifications:

**1. Summary** (string)
- 100-150 words concise executive summary
- **MANDATORY first sentence**: Acknowledge data reliability (e.g., "Analysis based on 5 annual and 8 quarterly periods with High reliability" or "Limited to 3 annual periods with Medium reliability—note limitations below")
- Include: investment thesis citing specific metrics (2-3 sentences), key decision factors with numbers, most critical risk
- **If data reliability is Medium or Low, state how this affects confidence in the ratings**

**2. Evaluation** (object)

- **Rating** (object with integer values 1-10 for each component) - Follow the Quantitative Anchoring Rules above

- **Rating_Justification** (object with string values) - NEW REQUIRED FIELD:
  - **Moat**: 1-2 sentences citing specific margin trends, ROE, or competitive advantages from the data
  - **Management**: 1-2 sentences citing FCF, debt management, or capital allocation decisions from the data
  - **Financials**: 1-2 sentences citing growth rates, margins, liquidity ratios from the data
  - **Valuation**: 1-2 sentences showing P/E comparison, PEG calculation, or multiple analysis from the data
  - **Industry**: 1-2 sentences citing competitive position evidence from growth rates or market data
  - Each justification MUST reference specific numbers from the provided financial data

- **Price_Target_Calculation** (object) - NEW REQUIRED FIELD:
  - **Method**: "P/E Multiple Approach" or "Price/Sales Approach" or "EV/EBITDA Approach"
  - **Current_Price**: The current price from the data (number)
  - **Trailing_PE**: From ticker_info.trailingPE (number, if available)
  - **Forward_PE**: From ticker_info.forwardPE (number, if available; use for comparison)
  - **Target_PE** (or multiple): Your chosen target multiple (number)
  - **Target_PE_Justification**: Why you chose this multiple (string)
  - **Latest_EPS** (or revenue/share, EBITDA): From latest period (number)
  - **Expected_Growth_Rate**: Justified from historical trends (decimal, e.g., 0.13 for 13%)
  - **Target_EPS** (or metric): Calculated forward estimate (number)
  - **Calculation**: Step-by-step math as a string (e.g., "22 × $6.89 = $151.58")
  - **Fair_Value**: Your calculated fair value price (number)

- **Recommendation** (string): "Strong Buy" / "Buy" / "Hold" / "Sell" / "Strong Sell"
  - Logic: Strong Buy if price <20% below fair value, Buy if <10% below, Hold if within ±10%, Sell if >10% above, Strong Sell if >20% above

- **Price Target Buy Below** (number): Typically Fair_Value × 0.80 to 0.90 (10-20% margin of safety)
- **Price Target Sell Above** (number): Typically Fair_Value × 1.15 to 1.25 (15-25% upside target)  
- **Price Stop Loss** (number): Typically Buy Price × 0.75 to 0.80 (20-25% maximum loss)

- **Price_Target_Rationale** (string): NEW REQUIRED FIELD - Explain your buy/sell/stop prices in 2-3 sentences, showing the math (e.g., "$130 buy price = $151 fair value × 0.86 for 14% margin of safety")

**3. Analysis** (string)
Comprehensive analysis covering:

- **Data Quality Assessment** (MANDATORY first paragraph):
  - State number of periods available (annual and quarterly)
  - Acknowledge missing metrics (if any)
  - Note any data quality concerns

- **Competitive Moat Assessment**: 
  - List 3-5 supporting factors
  - MUST cite specific margin trends (e.g., "Gross margin: 38% (2020) → 43% (2024)")
  - MUST cite ROE trend (e.g., "ROE averaged 23% over 5 years")
  - Reference switching costs, network effects only if financial evidence exists

- **Management Quality**: 
  - MUST cite FCF vs net income ratio (e.g., "FCF at 95% of net income indicates quality earnings")
  - MUST cite debt management (e.g., "D/E reduced from 0.5 to 0.3")
  - Capital allocation decisions with specific results

- **Financial Health**: 
  - MUST show revenue growth calculation (e.g., "Revenue: $2.1B (latest) vs $1.8B (prior year) = 18% YoY growth")
  - MUST show margin trends (e.g., "Net margin improved from 10% to 12%")
  - MUST cite liquidity ratios (e.g., "Current ratio: 2.1, indicating strong liquidity")
  - Cash generation quality with FCF numbers

- **Valuation Assessment** (MANDATORY detailed subsection):
  ```markdown
  ### Valuation Deep Dive
  **Current Metrics:**
  - Current Price: $[from data]
  - Trailing P/E: [from ticker_info.trailingPE]
  - Forward P/E: [from ticker_info.forwardPE if available]
  - Current PEG: [P/E / growth rate]
  
  **Fair Value Calculation:**
  [Show the calculation from Price_Target_Calculation above]
  - Target P/E: [number] (justified by [reason])
  - Target EPS: $[latest EPS] × [1 + growth rate] = $[result]
  - Fair Value: [Target P/E] × [Target EPS] = $[result]
  
  **Conclusion:** Current price of $[X] is [Y%] [above/below] fair value of $[Z]
  ```

- **Industry Position**: 
  - Compare revenue growth to own historical average if industry data unavailable
  - Competitive advantages backed by financial outperformance
  - Disruption risks with potential financial impact

- **Key Strengths**: 3-5 bullet points, each citing specific metrics

- **Overall Rating Interpretation**: 
  - State the average of 5 ratings as integer
  - Explain score meaning per guidelines

- **Recommendation Rationale**: 
  - Conviction level (High/Medium/Low)
  - Time horizon
  - 2-3 sentences tying together valuation vs. price and risk/reward

Use markdown formatting (headings, bullets, bold) for readability.

**4. Risks** (string)
Detailed risk assessment covering:

- **Financial Risks**: Leverage, liquidity, profitability pressure with potential impact
- **Operational Risks**: Execution, supply chain, cost inflation
- **Competitive Risks**: Market share loss, pricing pressure
- **Regulatory/Macro Risks**: Policy changes, economic sensitivity
- Each risk with specific potential impact assessment

Use markdown formatting (headings, bullets) for readability.

---

**Critical JSON Requirements:**
- Response must be VALID JSON only (no markdown code blocks, no extra text before/after)
- All string values must properly escape special characters (quotes, newlines, etc.)
- Ratings must be integers from 1-10 (no decimals)
- Price targets must be numeric values
- Use specific numbers from the financial data provided above
- Show calculations where relevant
- Acknowledge data limitations if historical periods are incomplete
- Be objective - highlight both positives and negatives
- Provide actionable insights, not generic commentary

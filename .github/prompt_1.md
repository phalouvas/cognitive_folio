# Initial Security Baseline Evaluation

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
- Historical data is incomplete (e.g., "Only 4 annual periods available instead of 10" for Yahoo Finance sources)
- Key metrics are missing (e.g., "P/E ratio not available, using P/S instead")
- Recent periods show data quality issues (e.g., "Latest quarter shows unusual items")
- Comparisons are limited (e.g., "No industry benchmarks available")

**Note on Data Sources:**
- **SEC Edgar (US companies)**: Expect 10+ annual and 16+ quarterly periods with high data quality
- **Yahoo Finance (non-US companies)**: Expect 4-5 annual and 5-8 quarterly periods - this is normal and should be acknowledged but not penalized

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

## Response Format - Human-Readable Analysis

Provide a comprehensive, well-structured analysis in **markdown format** with clear headings and sections. Use the following structure:

---

## Executive Summary

Write a concise 100-150 word summary that includes:
- **Data Quality Note**: State number of annual and quarterly periods available and data source (SEC Edgar or Yahoo Finance)
- **Investment Thesis**: 2-3 sentences with specific metrics supporting the core investment case
- **Key Decision Factors**: Critical numbers driving the recommendation (revenue growth, margins, valuation multiples)
- **Critical Risk**: The single most important risk to monitor

---

## Investment Ratings

Present ratings in a clear table format with justifications:

| Rating Category | Score | Justification |
|----------------|-------|---------------|
| **Competitive Moat** | X/10 | Cite specific gross margin trend and ROE with numbers |
| **Management Quality** | X/10 | Cite FCF conversion, D/E ratio changes, capital allocation evidence |
| **Financial Health** | X/10 | Cite revenue growth %, margin %, current ratio with specific numbers |
| **Valuation** | X/10 | Cite P/E ratios, PEG calculation, fair value vs current price |
| **Industry Position** | X/10 | Cite competitive positioning evidence from growth/margin data |
| **Overall Rating** | X/10 | Average of above 5 ratings, rounded to nearest integer |

**Rating Scale Interpretation:**
- 8-10: Strong/Excellent - Core portfolio holding
- 5-7: Good/Fair - Suitable for diversification
- 1-4: Weak/Poor - Avoid or reduce exposure

---

## Detailed Analysis

### Data Quality Assessment
- State exact number of annual and quarterly periods available
- Acknowledge any missing critical metrics
- Note data source and quality scores
- Highlight any data concerns or anomalies

### Competitive Moat Assessment
**Moat Strength: [Strong/Moderate/Weak]**

List 3-5 supporting factors with specific data:
- **Pricing Power**: Gross margin trend over time (e.g., "38% → 43% over 5 years")
- **Returns**: ROE trend with specific percentages
- **Market Position**: Evidence from financial outperformance
- **Barriers to Entry**: Only mention if financially evident (high R&D, capital requirements visible in data)
- **Customer Retention**: Evidence from revenue stability or growth patterns

### Management Quality Assessment
**Capital Allocation: [Excellent/Good/Fair/Poor]**

Evaluate using observable decisions:
- **Cash Generation**: FCF as % of net income with specific numbers
- **Leverage Management**: D/E ratio trends with specific values
- **Shareholder Returns**: Dividend growth, buyback patterns with amounts
- **Strategic Decisions**: M&A track record, capital investments with returns

### Financial Health Analysis
**Financial Strength: [Strong/Stable/Concerning]**

#### Revenue & Growth
- Latest revenue with YoY growth calculation and percentage
- Historical growth trend (3-5 year pattern)
- Growth acceleration/deceleration analysis

#### Profitability & Margins
- Gross margin: Latest % and trend
- Operating margin: Latest % and trend
- Net margin: Latest % and trend
- Margin expansion/contraction drivers

#### Balance Sheet Strength
- Current ratio: Specific value and interpretation
- D/E ratio: Specific value and trend
- Cash position and debt levels with amounts

#### Cash Flow Quality
- Operating cash flow: Latest amount and trend
- Free cash flow: Latest amount and FCF/Net Income ratio
- Capital expenditure patterns

### Valuation Assessment

#### Current Valuation Metrics
- Current Price: $[X]
- Trailing P/E: [X] (from data)
- Forward P/E: [X] (if available)
- PEG Ratio: [Calculate: P/E / growth rate] = [X]
- Price/Book: [X]
- EV/EBITDA: [X]

#### Fair Value Calculation
**Method Used**: [P/E Multiple / Price-to-Sales / EV/EBITDA]

**Step-by-Step Calculation:**
1. **Target Multiple**: [X] (justify based on growth, sector, historical)
2. **Earnings/Sales Metric**: $[Y] (latest or projected)
3. **Fair Value Formula**: [Multiple] × [Metric] = $[Result]
4. **Calculation**: Show the actual math

**Valuation Conclusion:**
- Fair Value: $[X]
- Current Price: $[Y]
- Discount/Premium: [Z]% [undervalued/overvalued]
- Margin of Safety: [+/-]%

### Industry Position Analysis
**Competitive Position: [Leading/Strong/Average/Weak]**

- Revenue growth vs historical average (cite specific %)
- Margin comparison to historical range
- Market share trends (if available in data)
- Competitive dynamics visible in financials

### Key Strengths
List 3-5 bullet points, each with specific supporting metrics:
- **Strength 1**: [Description with specific numbers]
- **Strength 2**: [Description with specific numbers]
- **Strength 3**: [Description with specific numbers]

### Key Weaknesses
List 2-4 bullet points, each with specific supporting data:
- **Weakness 1**: [Description with specific numbers]
- **Weakness 2**: [Description with specific numbers]

---

## Investment Recommendation

### Overall Assessment
**Recommendation: [Strong Buy / Buy / Hold / Sell / Strong Sell]**  
**Conviction Level: [High / Medium / Low]**  
**Investment Horizon: [Long-term (3+ years) / Medium-term (1-3 years) / Short-term (<1 year)]**

**Recommendation Rationale** (2-3 sentences):
Tie together valuation vs price, risk/reward profile, and key catalysts or concerns. Reference specific metrics that drive the recommendation.

### Price Targets

| Target Type | Price | Calculation Basis |
|------------|-------|-------------------|
| **Fair Value** | $[X] | Target multiple × projected metric |
| **Buy Below** | $[Y] | Fair value × 0.80-0.90 (10-20% margin of safety) |
| **Sell Above** | $[Z] | Fair value × 1.15-1.25 (15-25% upside target) |
| **Stop Loss** | $[W] | Buy price × 0.75-0.80 (20-25% max loss) |

**Price Target Rationale** (2-3 sentences):
Explain the margin of safety, upside potential, and risk protection embedded in these targets. Show the specific calculations (e.g., "$130 = $151 fair value × 0.86 for 14% safety margin").

### Position Sizing Guidance
- **Portfolio Weight**: [Recommended % based on conviction and risk]
- **Entry Strategy**: [All-at-once / Scale in over time / Wait for pullback]
- **Risk Management**: [Stop loss discipline / Position limits / Diversification notes]

---

## Risk Analysis

### Financial Risks
- **Leverage Risk**: [Assessment with D/E numbers and trend]
- **Liquidity Risk**: [Assessment with current ratio and cash position]
- **Profitability Risk**: [Assessment with margin trends and sensitivity]
- **Potential Impact**: Quantify potential earnings/valuation impact

### Operational Risks
- **Execution Risk**: [Specific operational challenges visible in data]
- **Supply Chain Risk**: [Evidence from inventory, margins, or cash flow]
- **Cost Inflation**: [Visible in margin compression or expense trends]
- **Potential Impact**: Estimate margin or revenue impact range

### Competitive Risks
- **Market Share Risk**: [Evidence from growth vs industry]
- **Pricing Pressure**: [Evidence from margin trends]
- **Disruption Risk**: [Assess from R&D spend, innovation metrics]
- **Potential Impact**: Revenue/margin sensitivity analysis

### Regulatory & Macro Risks
- **Regulatory Risk**: [Industry-specific compliance, policy exposure]
- **Economic Sensitivity**: [Cyclicality visible in historical data]
- **Interest Rate Risk**: [Debt levels, refinancing, valuation multiple sensitivity]
- **Potential Impact**: Scenario analysis for different environments

### Top 3 Critical Risks to Monitor
1. **[Risk Name]**: [Specific trigger points and early warning indicators]
2. **[Risk Name]**: [Specific trigger points and early warning indicators]
3. **[Risk Name]**: [Specific trigger points and early warning indicators]

---

## Monitoring & Review Plan

### Key Metrics to Track Quarterly
- [ ] Revenue growth rate (target: [X]%, red flag if <[Y]%)
- [ ] Gross margin (target: >[X]%, red flag if <[Y]%)
- [ ] Operating margin (target: >[X]%, red flag if <[Y]%)
- [ ] Free cash flow (target: >[X]% of net income)
- [ ] D/E ratio (target: <[X], red flag if >[Y])
- [ ] Current ratio (target: >[X], red flag if <[Y])

### Upcoming Catalysts
- [List specific events with dates: earnings releases, product launches, regulatory decisions]

### Investment Thesis Invalidation Triggers
List specific conditions that would require reassessment or exit:
- [ ] Revenue growth falls below [X]% for 2 consecutive quarters
- [ ] Gross margin compresses below [X]%
- [ ] D/E ratio exceeds [X]
- [ ] Stock price falls below $[X] (stop loss)
- [ ] [Other specific fundamental deterioration]

---

## Appendix: Calculation Details

### Fair Value Calculation Worksheet
[Provide detailed step-by-step calculation showing all assumptions and inputs]

### Historical Performance Summary
[Optional: Table summarizing 3-5 year trends in key metrics]

### Peer Comparison
[Optional: If industry benchmarks mentioned, show comparative table]

---

**Data Sources**: SEC Edgar (US companies) / Yahoo Finance (international)  
**Analyst Notes**: [Any additional context or disclaimers]

---

**Critical Guidelines for Response:**
- **Be Specific**: Every claim must cite exact numbers from the financial data
- **Be Concise**: Avoid repetition; each section should add unique value
- **Be Honest**: Acknowledge limitations, missing data, and uncertainties
- **Be Actionable**: Provide clear guidance with specific thresholds and triggers
- **Use Markdown Formatting**: Clear headings, tables, bullet points, and emphasis
- **Show Your Work**: All calculations must be transparent and verifiable
- **Balance Positives and Negatives**: Fair assessment of strengths AND weaknesses
- **Quantify Everything**: Use numbers, percentages, ratios - not vague descriptions

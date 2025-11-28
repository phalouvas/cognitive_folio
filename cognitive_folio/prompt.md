# Comprehensive Security Evaluation

## Security Overview
**Company:** {{security_name}} ({{symbol}})  
**Sector:** {{sector}}  
**Industry:** {{industry}}  
**Market Cap:** {{ticker_info.marketCap}}  
**Current Price:** {{current_price}} {{currency}}

---

## Historical Annual Performance (5 Years)
{{periods:annual:5:markdown}}

---

## Recent Quarterly Trends (8 Quarters)
{{periods:quarterly:8:markdown}}

---

## Period Comparisons

### Latest Annual vs Previous Annual
{{periods:compare:latest_annual:previous_annual}}

### Latest Annual vs 2 Years Ago
{{periods:compare:latest_annual:annual_minus_2}}

### Latest Quarter vs Previous Quarter
{{periods:compare:latest_quarterly:previous_quarterly}}

### Latest Quarter vs Year-Ago Quarter (YoY)
{{periods:compare:latest_quarterly:yoy_quarterly}}

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

## Recent News & Sentiment
{{news.ARRAY.content.title}}

**News Details:**
{{news.ARRAY.content.summary}}

---

## Analysis Instructions

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
  "Summary": "A concise executive summary (100-150 words) covering the investment thesis in 2-3 sentences, key decision factors for buy/hold/sell, and the most critical risk to monitor.",
  "Evaluation": {
    "Rating": {
      "Moat": 7,
      "Management": 8,
      "Financials": 7,
      "Valuation": 6,
      "Industry": 8
    },
    "Recommendation": "Strong Buy",
    "Price Target Buy Below": 150.00,
    "Price Target Sell Above": 200.00,
    "Price Stop Loss": 120.00
  },
  "Analysis": "Detailed analysis text here covering all aspects...",
  "Risks": "Key risks text here..."
}
```

### JSON Field Specifications:

**1. Summary** (string)
- 100-150 words concise executive summary
- Include: investment thesis (2-3 sentences), key decision factors, most critical risk

**2. Evaluation** (object)
- **Rating** (object with integer values 1-10 for each component):
  - **Moat**: Competitive moat strength (1-10). Consider: network effects, switching costs, brand value, cost advantages, regulatory barriers. Use specific metrics from financial data.
  - **Management**: Management quality (1-10). Evaluate: capital allocation (M&A, buybacks, dividends), transparency, track record vs promises, evidence from financial results.
  - **Financials**: Financial health (1-10). Assess: profitability trends (margins, ROE, ROA), leverage (D/E, interest coverage), liquidity (current ratio, cash), cash generation quality (FCF vs net income).
  - **Valuation**: Valuation attractiveness (1-10). Compare current multiples to: historical averages, industry peers, growth rates (PEG). Include fair value estimate vs current price.
  - **Industry**: Industry position (1-10). Consider: market share trends, competitive advantages vs peers, disruption risks, industry growth outlook.
  
  **Rating Scale Guide:**
  - 9-10: Exceptional/Outstanding
  - 7-8: Strong/Above Average
  - 5-6: Average/Fair
  - 3-4: Below Average/Weak
  - 1-2: Poor/Critical Issues

- **Recommendation** (string): Choose one: "Strong Buy", "Buy", "Hold", "Sell", or "Strong Sell"
- **Price Target Buy Below** (number): Specific buy price with margin of safety
- **Price Target Sell Above** (number): Upside target price based on valuation model
- **Price Stop Loss** (number): Downside protection level for risk management

**3. Analysis** (string)
Comprehensive analysis covering:

- **Competitive Moat Assessment**: List 3-5 supporting factors with evidence from financial data
- **Management Quality**: Capital allocation decisions, transparency, execution track record with specific examples
- **Financial Health**: Profitability trends, leverage assessment, liquidity position, cash generation quality with specific numbers
- **Valuation Assessment**: Current multiples vs historical averages and peers, fair value calculation showing your work (e.g., "Current P/E of 25 vs 5-year avg of 20")
- **Industry Position**: Market share trends, competitive advantages, disruption risks
- **Key Strengths**: 3-5 bullet points with specific metrics from financial data
- **Overall Rating Interpretation**: The average of the 5 component ratings. Explain what this score means (e.g., "Strong investment candidate" for 8+, "Average quality" for 5-7, "Caution advised" for <5)
- **Recommendation Rationale**: State conviction level (High/Medium/Low), time horizon (short-term <1yr, medium-term 1-3yr, long-term >3yr), 2-3 sentence rationale

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

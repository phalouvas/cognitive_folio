# Security Update - Quarterly/Annual Results

## PREREQUISITE: Baseline Evaluation Required

**STOP AND CHECK**: Does the **immediately previous message** in this chat contain an **Initial Security Baseline Evaluation** or a prior **Security Update - Quarterly/Annual Results**?

- **If NO**: ❌ Cannot proceed. You need an initial security analysis as baseline to compare against.
  - **Response to user**: "Cannot proceed with quarterly update. An Initial Security Baseline Evaluation is required as baseline. Please provide initial security analysis first."
  - **User action**: Start a new message with Initial Security Baseline Evaluation for the security.

- **If YES**: ✅ Proceed. Reference ONLY the immediately previous message for baseline ratings and metrics. Do not search chat history further.

---

## Security Context
**Company:** {{security_name}} ({{symbol}})  
**Sector:** {{sector}}  
**Industry:** {{industry}}  
**Current Price:** {{current_price}} {{currency}}  
**Market Cap:** {{ticker_info.marketCap}}

---

## Financial Statements (Latest Quarter)
The following JSON contains structured financial data for the most recent quarter:

```json
{{financials:y0:q1}}
```

---

## Current Valuation Metrics
- **Trailing P/E:** {{ticker_info.trailingPE}}
- **Forward P/E:** {{ticker_info.forwardPE}}
- **Price to Book:** {{ticker_info.priceToBook}}
- **PEG Ratio:** {{ticker_info.pegRatio}}
- **Beta:** {{ticker_info.beta}}

---

## Data Reliability Assessment

**BEFORE ANALYSIS**: Assess current data quality and note any changes:

1. **Critical Fields Check**: Are key metrics populated in latest periods?
   - Income Statement: revenue, net income, operating income
   - Balance Sheet: assets, liabilities, equity
   - Cash Flow: operating cash flow, free cash flow
   - Valuation: P/E, current price

2. **Inconsistency Detection**: Look for red flags in latest data:
   - Unusual swings in revenue or margins (possible data error or real business change?)
   - Missing data points
   - Gaps in historical continuity

3. **Data Reliability Rating** (for this update):
   - **High**: All key fields populated, consistent with prior periods, no anomalies
   - **Medium**: 70-90% of fields populated, minor gaps, data looks reasonable
   - **Low**: <70% of fields populated, inconsistencies, data questionable

**If data reliability is Medium or Low, flag it explicitly and state impact on rating confidence.**

---

## Analysis Context

**IMPORTANT - Reference Previous Message Only**: 

The baseline **Initial Security Baseline Evaluation** (or most recent **Security Update - Quarterly/Annual Results**) is in the **immediately previous message above this one**. 

- Extract the baseline ratings from that message: Moat, Management, Financials, Valuation, Industry
- Note the baseline recommendation and price targets from that message
- Compare current period data to what was analyzed in that message
- Assess if delta is material enough to warrant rating adjustments

**Do not search or reference older messages in chat history.**

---

## Quantitative Change Detection Rules

**CRITICAL**: This is an incremental update focusing on **what changed**. You must cite specific numbers comparing latest period to previous period.

### Change Detection Methodology

**Revenue & Earnings Changes** (MANDATORY):
- Calculate QoQ change: (Latest Quarter - Previous Quarter) / Previous Quarter × 100
- Calculate YoY change: (Latest Quarter - Year Ago Quarter) / Year Ago Quarter × 100
- State both absolute change ($) and percentage change (%)
- Example: "Revenue: $525M (Q4) vs $490M (Q3) = +$35M or +7.1% QoQ; vs $455M (Q4 last year) = +$70M or +15.4% YoY"

**Margin Changes** (MANDATORY if margins provided):
- Calculate basis point changes in gross, operating, and net margins
- Example: "Gross margin: 43.2% (Q4) vs 41.8% (Q3) = +140 bps improvement"
- Explain drivers if identifiable from the data (volume, pricing, cost efficiency)

**Balance Sheet Changes** (if annual data available):
- Calculate change in cash, debt, working capital
- Example: "Cash: $800M vs $650M prior year = +$150M or +23%"
- Calculate change in debt-to-equity ratio
- Example: "D/E: 0.28 vs 0.35 prior year = deleveraging trend"

### Rating Adjustment Philosophy

**Use Reasoning to Assess Materiality**: For each rating, evaluate if the delta from the previous message is material enough to warrant adjustment:
- Is this metric change significant relative to business cycle and volatility?
- Has the fundamental competitive position shifted?
- Is this trend reversal (inflection) or normal quarterly noise?
- Show your reasoning—don't adjust ratings for minor or expected fluctuations.

**Prohibited Behaviors**

- ❌ **NO full re-evaluation**: Don't repeat entire investment thesis - focus on what's NEW
- ❌ **NO vague changes**: Don't say "revenue grew" without stating exact % QoQ and YoY
- ❌ **NO rating changes without justification**: Must cite which metric changed and why it's material
- ❌ **NO ignoring negative changes**: If margins declined or growth slowed, address it explicitly
- ❌ **NO assumptions**: If you don't see the change in the data, state "No significant change observed"

---

## Update Analysis Instructions

**IMPORTANT:** This is an incremental update, not a full re-evaluation. Focus exclusively on **changes and new developments** since the previous message (Initial Security Baseline Evaluation or prior Security Update - Quarterly/Annual Results).

### Required Analysis Output:

**1. Financial Performance Update** (100-150 words)

**MANDATORY Format - Use exact calculations from comparison data:**

- **Revenue & Earnings:** 
  - QoQ: $[Latest] vs $[Previous] = [+/- %] change
  - YoY: $[Latest] vs $[Year Ago] = [+/- %] change
  - EPS: $[Latest] vs $[Previous] (QoQ) and vs $[Year Ago] (YoY)
  - Assessment: Beat/miss vs historical trend (state the trend rate)

- **Margin Analysis:** 
  - Gross margin: [Latest %] vs [Previous %] = [+/- X] basis points
  - Operating margin: [Latest %] vs [Previous %] = [+/- X] basis points
  - Net margin: [Latest %] vs [Previous %] = [+/- X] basis points
  - Driver analysis if identifiable

- **Balance Sheet Changes:** 
  - Cash: $[Latest] vs $[Previous Period] = [+/- %]
  - Debt: $[Latest] vs $[Previous Period] = [+/- %]
  - D/E ratio: [Latest] vs [Previous]

- **Cash Flow Quality:** 
  - Operating cash flow: $[Latest] vs $[Previous]
  - FCF: $[Latest] vs $[Previous]
  - FCF as % of net income: [calculate if data available]

**2. Business & Strategic Developments** (75-100 words)
- **New Products/Services:** Launches, expansions, or discontinuations
- **Management Changes:** CEO, CFO, or other key executive changes
- **M&A Activity:** Acquisitions, divestitures, or strategic partnerships announced
- **Market Expansion:** Geographic expansion, new customer segments, channel changes
- **Operational Changes:** Plant closures/openings, restructuring, efficiency initiatives
- **Competitive Dynamics:** Market share gains/losses, new competitors, pricing changes

**3. News Impact Assessment** (50-75 words)
- Identify the most material news items from above
- Assess positive vs negative sentiment
- Evaluate potential impact on fundamentals (revenue, margins, market position)
- Note any regulatory, legal, or reputational developments

**4. Rating Adjustments** (if material changes warrant)

**REFERENCE PREVIOUS MESSAGE**: Check the baseline Moat/Management/Financials/Valuation/Industry ratings from the immediately previous message.

For each of the 5 core ratings, evaluate if an adjustment is needed:

- **Competitive Moat:** [New Rating X/10 if changed, or "No change - remains at [previous rating]/10"]
  - **Assessment**: Did gross margin, ROE, or pricing power meaningfully shift? Is it material?
  - If changed: "Rating adjusted from [previous] to [new] because [specific metric change with numbers and reasoning]"
  - Example: "Upgraded from 6 to 7 because gross margin expanded from 38% to 42% (+400 bps), indicating strengthening pricing power and sustained competitive advantage."
  
- **Management Quality:** [New Rating X/10 if changed, or "No change - remains at [previous rating]/10"]
  - **Assessment**: Major capital allocation decision announced? Debt changed significantly? FCF quality shifted?
  - If changed: Cite specific decision and financial result
  - Example: "Downgraded from 8 to 7 due to $500M acquisition at 15x EBITDA (above historical 10x average), suggesting less disciplined capital allocation."
  
- **Financial Health:** [New Rating X/10 if changed, or "No change - remains at [previous rating]/10"]
  - **Assessment**: Revenue growth acceleration/deceleration material? Margin compression concerning? Leverage increased significantly?
  - If changed: "Rating adjusted from [previous] to [new] because [specific financial metric change with numbers and reasoning]"
  - Example: "Upgraded from 6 to 7 as revenue growth accelerated from 8% to 18% YoY and net margin expanded from 10% to 12%, indicating operational leverage kicking in."
  
- **Valuation:** [New Rating X/10 if changed, or "No change - remains at [previous rating]/10"]
  - **Assessment**: Stock price moved materially? P/E multiple changed significantly? EPS estimate revised?
  - If changed: Recalculate fair value implications and show new discount/premium
  - Example: "Downgraded from 7 to 6. Stock rose from $145 to $165 (+14%), now trading at 27x P/E vs 22x fair value (23% overvaluation vs prior 4% undervaluation)."
  
- **Industry Position:** [New Rating X/10 if changed, or "No change - remains at [previous rating]/10"]
  - **Assessment**: Growth rate changed vs own history significantly? Major competitive development? Market share news?
  - If changed: Cite specific competitive metric change
  - Example: "Maintained at 8/10. Revenue growth of 18% YoY consistent with prior quarters (16-19% range). No material competitive changes."

- **Overall Rating:** [Calculate new average if any ratings changed: (sum of 5 ratings) / 5, rounded to nearest integer]
  - Reference previous overall rating from previous message for comparison
  - Show calculation: (Moat + Management + Financials + Valuation + Industry) / 5 = [X]/10
  - State: "Overall rating [increased/decreased/unchanged] from [previous]/10 to [new]/10"

**5. Recommendation Update**
- **Previous Recommendation:** [Reference from previous message in chat]
- **Current Recommendation:** [Strong Buy / Buy / Hold / Sell / Strong Sell]
- **Change from Previous:** [Upgraded / Downgraded / Maintained]
- **Conviction Level:** [High / Medium / Low] (was [previous conviction level])
- **Rationale:** 2-3 sentences explaining the recommendation in light of new developments
- **Position Sizing Guidance:** Should investors add, hold, trim, or exit? Why?

**6. Updated Price Targets** (if warranted by new data)

**RECALCULATION CRITERIA**: Recalculate only if material changes warrant:
- Stock price moved >10% since previous evaluation
- EPS estimate changed >10% based on new results
- P/E multiple assumption changed >2 points
- Material change in risk profile or competitive position

**If recalculation needed, show your work:**

```
Previous Fair Value Calculation (from previous message):
- Target P/E: [X] × Target EPS: $[Y] = $[Z] fair value

Updated Fair Value Calculation:
- New Target P/E: [X] (changed because [reason] or unchanged)
- New Target EPS: $[Y] (was $[old], updated by [%] due to [results])
- New Fair Value: [P/E] × [EPS] = $[result]

Updated Targets:
- Buy Below: $[fair value × 0.85] (was $[old])
- Sell Above: $[fair value × 1.20] (was $[old])
- Stop Loss: $[buy × 0.75] (was $[old])
```

**If no recalculation needed:**
- **Buy Price:** No change - remains $[XX from previous analysis]. Fair value methodology still valid based on [current P/E / growth rate / etc.]
- **Sell Price:** No change - remains $[XX from previous analysis]. Upside target still appropriate.
- **Stop Loss:** No change - remains $[XX from previous analysis]. Risk parameters unchanged.
- **Rationale:** Briefly state why targets remain valid (e.g., "Price moved only 5%, within expected range" or "New EPS in line with projections")

**7. Key Monitoring Points for Next Quarter**
List 2-4 specific items to watch:
- Specific financial metrics to track (e.g., "Gross margin must stay above 45%")
- Upcoming events or catalysts (e.g., "Product launch in Q2", "Regulatory decision expected")
- Red flags to monitor (e.g., "Customer concentration risk if top client >25% of revenue")
- Positive developments to confirm thesis (e.g., "New market penetration should show in revenue mix")

**8. Quick Summary** (2-3 sentences)
- Bottom line: Is the investment thesis still intact, strengthening, or weakening? (Reference previous message baseline)
- Most important takeaway from this quarter's results
- Any immediate action needed?
- How does this update affect the ratings from the previous message?

---

**Critical Guidelines:**
- **Be Concise:** Total analysis should be 400-600 words (not including the data sections above)
- **Focus on Changes ONLY:** Don't repeat information that hasn't changed since previous message
- **MANDATORY Number Usage:** Every claim must cite specific figures from the comparison data
  - ✅ GOOD: "Revenue grew 15.4% YoY from $455M to $525M"
  - ❌ BAD: "Revenue showed strong growth"
- **Be Actionable:** Provide clear guidance (Add to position / Hold / Trim / Exit) with specific reasons
- **Acknowledge Limitations:** If comparison data is incomplete or has reliability issues, state it explicitly
- **Maintain Objectivity:** Give equal weight to positive and negative changes
- **Reference Previous Message**: Quote baseline ratings/targets from previous message when making comparisons

**Change Detection Checklist** - You MUST address:
1. ✅ Revenue: QoQ % and YoY % with $ amounts
2. ✅ Margins: Basis point changes in gross/operating/net margins
3. ✅ EPS: Absolute change and % change QoQ and YoY
4. ✅ Balance sheet: Material changes (>15%) in cash, debt, or key items
5. ✅ News impact: Which news items are material vs noise
6. ✅ Rating adjustments: Which ratings changed and why (or explicitly state "no changes warranted")
7. ✅ Price targets: Recalculate if thresholds met, or state "remain valid"

**Prohibited Behaviors:**
- ❌ **NO generic statements**: "Company performing well" without specific metrics
- ❌ **NO rating changes without material reason**: Must show delta from baseline in previous message
- ❌ **NO price target changes without calculation**: Must show updated math if changing targets
- ❌ **NO repeating full thesis**: This is an UPDATE, not a comprehensive analysis
- ❌ **NO ignoring negative data**: If metrics worsened, address it directly with numbers
- ❌ **NO referencing older messages**: Only use immediately previous message (Prompt_1 baseline or latest Prompt_2 update)

**How to Use This Prompt:**
1. First message: Use Initial Security Baseline Evaluation to establish baseline ratings and investment thesis
2. Follow-up messages: Use this Security Update - Quarterly/Annual Results prompt to analyze changes since the previous message
3. The AI will reference the immediately previous message for baseline context and assess deltas

**When to Use This Prompt:**
- After quarterly earnings releases (within 1-2 weeks)
- After annual report publication
- When significant news breaks (major M&A, management changes, regulatory actions)
- As a regular check-in (every 3 months if no major news)
- **ALWAYS in the same chat thread as the baseline Initial Security Baseline Evaluation**

**When to Start a New Chat with Initial Security Baseline Evaluation Instead:**
- When adding a new security to portfolio (initial evaluation - no prior analysis exists)
- When you want to completely re-baseline annual review (fresh perspective)
- When major structural changes occur (business model pivot, industry disruption - warrants full re-evaluation)

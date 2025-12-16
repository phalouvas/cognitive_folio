# Financial Analysis Refactor - Implementation Specification

## Overview
Refactor the AI analysis workflow to separate analytical calculations from qualitative AI interpretation. This reduces API calls, improves consistency, and provides transparent reasoning.

---

## 1. Financial Ratios to Calculate (Final)

### A. Liquidity Ratios (Health - can company pay short-term obligations?)
| Ratio | Formula | Range | Interpretation |
|-------|---------|-------|-----------------|
| **Current Ratio** | Current Assets / Current Liabilities | 1.5-3.0 ideal | >1.5 is healthy; <1.0 is risky |
| **Quick Ratio** | (Current Assets - Inventory) / Current Liabilities | 0.8-2.0 ideal | More conservative than current ratio |
| **Working Capital** | Current Assets - Current Liabilities | >0 | Positive = healthy operations |
| **Working Capital Ratio** | Working Capital / Revenue | 10-20% | Efficiency of capital use |

### B. Profitability Ratios (Earnings quality & management efficiency)
| Ratio | Formula | Notes |
|-------|---------|-------|
| **Net Profit Margin** | Net Income / Revenue | Higher = better; track YoY trend |
| **Gross Profit Margin** | Gross Profit / Revenue | Industry-dependent; compare vs peers |
| **Operating Margin** | Operating Income / Revenue | Core business profitability |
| **Return on Assets (ROA)** | Net Income / Total Assets | How efficiently assets generate profit |
| **Return on Equity (ROE)** | Net Income / Shareholders' Equity | How efficiently capital generates profit |
| **Return on Invested Capital (ROIC)** | NOPAT / Invested Capital | If available; otherwise `null` |

### C. Efficiency Ratios (Asset utilization)
| Ratio | Formula | Notes |
|-------|---------|-------|
| **Asset Turnover** | Revenue / Average Total Assets | Revenue generated per dollar of assets |
| **Receivables Days** | (Current Receivables / Revenue) × 365 | If receivables not present → `null` |

### D. Growth Metrics (Trajectory - is the company growing?)
| Metric | Calculation | Notes |
|--------|-------------|-------|
| **Revenue Growth %** | (Current Year Revenue - Prior Year) / Prior Year × 100 | YoY % change; track 3-5 year trend |
| **Earnings Growth %** | (Current Year Net Income - Prior Year) / Prior Year × 100 | YoY % change; quality of growth |
| **EPS Growth %** | Year-over-year earnings per share change | Requires shares outstanding; else `null` |

### E. Valuation Ratios (Is stock fairly priced?)
| Ratio | Formula | Notes |
|-------|---------|-------|
| **Price-to-Earnings (P/E)** | Current Price / EPS | Lower = potentially undervalued; compare to industry |
| **Price-to-Book (P/B)** | Current Price / Book Value Per Share | Lower = potentially undervalued vs assets |
| **Dividend Yield** | Annual Dividend Per Share / Current Price × 100 | If dividend data absent → `null` |
| **Payout Ratio** | Dividends / Net Income × 100 | % of earnings returned to shareholders |

### F. Debt & Financial Health (Leverage - solvency risk)
| Ratio | Formula | Safe Range | Notes |
|-------|---------|-----------|-------|
| **Debt-to-Equity (D/E)** | Total Debt / Shareholders' Equity | <1.0-2.0 | <1.0 = conservative; >2.0 = risky |
| **Debt-to-Assets** | Total Debt / Total Assets | <0.6 | % of assets financed by debt |
| **Interest Coverage** | EBIT / Interest Expense | >2.5 | If interest not available → `null` |
| **Free Cash Flow (FCF)** | Operating Cash Flow - Capital Expenditures | >0 | Cash available after reinvestment |

### G. Quality & Stability Indicators (Earnings reliability)
| Metric | Calculation | Notes |
|--------|-------------|-------|
| **Earnings Stability** | Std Dev of Net Income over 5 years / Avg Net Income | Lower = more stable |
| **FCF Conversion** | Free Cash Flow / Net Income | >1.0 = high-quality earnings |
| **Revenue Consistency** | YoY revenue growth variance | Low variance = stable, predictable business |

### H. Market-based Indicators (Optional, if available in `ticker_info`)
| Metric | Calculation | Notes |
|--------|-------------|-------|
| **Beta** | From market data | Volatility vs market; if unavailable → `null` |
| **EV/EBITDA** | Enterprise Value / EBITDA | If EV/EBITDA fields present; else `null` |

---

## 2. Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  fetch_data(with_fundamentals=True)                        │
│  Called by: Portfolio.run_price_fetch_news_evaluation()    │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
    ┌─────────────┐        ┌──────────────────┐
    │ Extract     │        │ Calculate Fair   │
    │ Financial   │        │ Value (existing) │
    │ Data (AI)   │        │                  │
    └──────┬──────┘        └──────┬───────────┘
           │                      │
           │    ┌─────────────────┘
           │    │
           ▼    ▼
    ┌───────────────────────────────────────┐
    │ calculate_financial_ratios() [NEW]     │
    │  - Parse financials from fetched_data │
    │  - Calculate all ratios above          │
    │  - Return ratio dict (null if missing) │
    └──────────────────┬────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ Merge into fetched_data:    │
         │  {                          │
         │    ticker_info: {...},      │
         │    annual_data: {...},      │
         │    quarterly_data: {...},   │
         │    financial_ratios: {...}  │  ◄─ NEW
         │  }                          │
         └──────────────────┬──────────┘
                            │
                            ▼
         ┌──────────────────────────────────────┐
         │ generate_ai_analysis() [MODIFIED]     │
         │  Input: fetched_data + fair_value    │
         │  Prompt: generate_analysis.md        │
         │  Model: deepseek-chat                │
         │  Temperature: 0.1 (consistent)       │
         └──────────────────┬───────────────────┘
                            │
            ┌───────────────┴──────────────────┐
            ▼                                  ▼
    ┌──────────────────┐         ┌────────────────────┐
    │ AI Response      │         │ Populate Fields:   │
    │ (human readable) │         │  - rating_moat     │
    │ Saved in:        │         │  - rating_mgmt     │
    │ ai_response (JSON)          │  - rating_industry │
    └──────────────────┘         │  - rating_valuation│
                                 │  - suggestion_*    │
                                 │  - suggestion_action
                                 └────────────────────┘
```

### Field Mappings (Ratings are integers 1-10)

| Source | Target | Type | Notes |
|--------|--------|------|-------|
| AI Response JSON | `ai_response` | JSON | Full AI output (stored as-is for audit) |
| AI Response → `Summary` | Converted to Markdown | `ai_suggestion` | For display |
| AI Response → `Evaluation.Moat` (1-10) | `rating_moat` | Rating | Directly from AI |
| AI Response → `Evaluation.Management` (1-10) | `rating_management` | Rating | Directly from AI |
| AI Response → `Evaluation.Industry` (1-10) | `rating_industry` | Rating | Directly from AI |
| AI Response → `Evaluation.Financials` (1-10) | `rating_financials` | Rating | Derived by AI using ratios |
| AI Response → `Evaluation.Valuation` (1-10) | `rating_valuation` | Rating | Directly from AI |
| AI Response → `Action` | `suggestion_action` | Select | Buy/Hold/Sell |
| Fair Value (existing calc) | `suggestion_fair_value` | Currency | Pass-through |
| Fair Value × 0.85 (15% margin of safety) | `suggestion_buy_price` | Currency | Calculated |
| Fair Value × 1.20 (20% profit target) | `suggestion_sell_price` | Currency | Calculated |
| Fair Value × 0.90 (10% stop loss) | `evaluation_stop_loss` | Currency | Calculated |
| round((valuation + financials + moat)/3) | `suggestion_rating` | Rating | Composite (1-10 scale) |

---

## 3. AI Model & Parameters

### Model Selection: **deepseek-chat** (final)

**Rationale:**
- ✅ Used consistently in `process_security_ai_suggestion()` and `extract_financial_data()`
- ✅ Optimized for structured JSON output (used in extraction prompt)
- ✅ Good at analytical reasoning with numerical data
- ✅ Cost-effective
- ✅ Maintains consistency across codebase

### Temperature Settings

**Temperature: 0.1** (deterministic, slight variation allowed)

**Rationale:**
- `0.0` = completely deterministic (may produce repetitive text, less natural)
- `0.1` = highly consistent **[CHOSEN]** with minimal randomness
  - Same input → ~95-99% same output
  - Slight variation prevents artifact patterns
  - Better text quality than 0.0
- `0.3` = moderate consistency (different each time, not ideal)
- `0.5+` = high variance (not acceptable for financial analysis)

### Other Parameters

```python
model = "deepseek-chat"
temperature = 0.1
top_p = 0.95  # Nucleus sampling; focus on high-probability tokens
presence_penalty = 0.0  # Allow repetition if necessary
frequency_penalty = 0.0  # Natural language, not restricted
json_mode = True  # enforce JSON-only output
```

### Response Format

```json
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
        "BuyBelowPrice": <number or null>,
        "SellAbovePrice": <number or null>
    },
    "Summary": "...",
    "Risks": ["..."],
    "Analysis": "..."
}
```

---

## 4. New Method: `calculate_financial_ratios()`

### Location
`/cognitive_folio/cognitive_folio/doctype/cf_security/cf_security.py`

### Signature
```python
def calculate_financial_ratios(self):
    """
    Calculate financial ratios from extracted financial data.
    
    Returns:
        dict: Comprehensive ratio analysis with the following structure:
        {
            "liquidity": {
                "current_ratio": float,
                "quick_ratio": float,
                "working_capital": float,
                "working_capital_ratio": float
            },
            "profitability": {
                "net_profit_margin": float,
                "gross_profit_margin": float,
                "operating_margin": float,
                "roa": float,
                "roe": float,
                "roic": float or null
            },
            "efficiency": {
                "asset_turnover": float,
                "receivables_days": float
            },
            "growth": {
                "revenue_growth_5y": [float],  # Last 5 years
                "earnings_growth_5y": [float],
                "eps_growth_5y": [float]
            },
            "valuation": {
                "pe_ratio": float,
                "pb_ratio": float,
                "dividend_yield": float,
                "payout_ratio": float
            },
            "debt_health": {
                "debt_to_equity": float,
                "debt_to_assets": float,
                "interest_coverage": float,
                "free_cash_flow": float
            },
            "quality": {
                "earnings_stability": float,  # 0-1 scale
                "fcf_conversion": float,
                "revenue_consistency": float
            },
            "data_quality": {
                "annual_periods": int,
                "quarterly_periods": int,
                "coverage": "High|Medium|Low"
            }
        }
    """
```

### Data Source
- Parse `self.profit_loss`, `self.balance_sheet`, `self.cash_flow` (already extracted)
- Use `self.current_price` for valuation ratios
- Use `self.dividends` for dividend metrics

### Handling Missing Data
- **If entire year is missing**: skip that data point
- **If field within a year is missing**: use `null` for that ratio
- **If insufficient data (e.g., <2 years)**: return `null` for trend-based metrics
- **Division by zero**: return `null`, not exception
- Minimum 2 years required for growth calculations

### Error Handling
```python
try:
    # ratio calculation logic
except Exception as e:
    frappe.log_error(f"Error calculating ratios for {self.symbol}: {str(e)}")
    return {"error": str(e), "ratios": None}
```

---

## 5. Modified Method: `generate_ai_analysis()`

### Current Flow
```python
@frappe.whitelist()
def generate_ai_analysis(self):
    """Generate AI analysis using financial ratios + qualitative assessment"""
    
    # Step 1: Ensure financial data extracted
    if not self.fetched_data:
        self.fetch_data(with_fundamentals=True)
    
    # Step 2: Calculate ratios
    ratios = self.calculate_financial_ratios()
    
    # Step 3: Merge into fetched_data
    fetched_data_dict = frappe.parse_json(self.fetched_data) or {}
    fetched_data_dict['financial_ratios'] = ratios
    self.fetched_data = frappe.as_json(fetched_data_dict)
    
    # Step 4: Build prompt from template
    prompt = self._build_analysis_prompt(ratios)
    
    # Step 5: Call AI
    ai_response = self._call_ai_analysis(prompt)
    
    # Step 6: Parse response & populate fields
    self._parse_ai_response(ai_response)
    
    # Step 7: Set alerts & save
    self.set_alert()
    self.save()
    
    return {"status": "success", "analysis": self.ai_suggestion_html}
```

### Background Job (existing pattern)
```python
@frappe.whitelist()
def process_portfolio_ai_analysis(portfolio_name, user):
    """Process AI analysis as background job (queue: long)"""
    try:
        security = frappe.get_doc("CF Security", security_name)
        security.generate_ai_analysis()
        # ... logging & notifications
    except Exception as e:
        frappe.log_error(...)
```

---

## 6. Prompt Template: `generate_analysis.md` [NEW]

### Structure (from scratch; enforce integers 1-10)
```markdown
# Deterministic Investment Analysis Prompt

You are an investment analyst. Use ONLY the provided JSON data. Do not guess missing values. If a required value is missing, use null.

## INPUT JSON
{{merged_json_fetched_data_with_financial_ratios}}

## TASKS
1. Evaluate the company on five dimensions: Moat, Management, Financials, Valuation, Industry.
2. Each rating MUST be an integer 1–10. No decimals.
3. Use the analytical ratios to justify Financials and Valuation ratings.
4. Derive Buy/Hold/Sell action deterministically:
     - If `current_price <= suggestion_buy_price` → Buy
     - Else if `current_price >= suggestion_sell_price` → Sell
     - Else → Hold
5. If `suggestion_buy_price` or `suggestion_sell_price` is missing, compute using policy in Section 8.

## OUTPUT (VALID JSON ONLY)
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
        "BuyBelowPrice": <number or null>,
        "SellAbovePrice": <number or null>
    },
    "Summary": "2-3 sentences",
    "Risks": ["...", "..."],
    "Analysis": "Short justification using ratios and data"
}

## STRICT RULES
- Ratings are integers 1–10 only.
- Use null for any missing metric.
- Base all statements on provided data (no external info).
- Output MUST be valid JSON. No markdown, no commentary.
```

---

## 7. Implementation Checklist

### Phase 1: Analytical Calculations
- [ ] Create `calculate_financial_ratios()` method
- [ ] Test with 3 sample securities (US, INTL, ETF)
- [ ] Verify null handling for sparse data
- [ ] Update `fetched_data` merge logic in `fetch_data()`

### Phase 2: AI Analysis Prompt
- [ ] Create `prompts/generate_analysis.md`
- [ ] Create `_build_analysis_prompt()` helper to populate variables
- [ ] Define ratio aggregation scores (liquidity_score, etc.)
- [ ] Test prompt with 2-3 securities

### Phase 3: Modify `generate_ai_analysis()`
- [ ] Integrate ratio calculation
- [ ] Implement prompt builder
- [ ] Call AI with deepseek-chat, temperature=0.1
- [ ] Parse JSON response
- [ ] Map to `rating_*` and `suggestion_*` fields
- [ ] Create `_parse_ai_response()` helper

### Phase 4: Testing & Validation
- [ ] Unit tests for ratio calculations
- [ ] Integration test: fetch_data → analyze → fields populated
- [ ] Consistency test: run twice, verify same output
- [ ] Error scenarios: missing data, zero divisions, etc.

---

## 8. Migration Notes

### Backward Compatibility
- Existing `generate_ai_suggestion()` method can coexist
- `generate_ai_analysis()` is new, can be called separately
- No breaking changes to DocType schema

### Performance
- Ratio calculation: ~10-50ms (CPU-bound, no API calls)
- AI analysis: ~2-5sec (API latency + token processing)
- Total per security: ~3-6 seconds

### Cost
- Reduced API calls: ✅ One AI call per analysis (not two)
- Token savings: ~20-30% fewer tokens (pre-calculated ratios are concise)
- Estimated savings: 30-50% per security analyzed

---

## 9. Margin of Safety & Price Policy (Final)

Deterministic policy to compute price targets (used when AI does not supply or to cross-check AI outputs):

- Risk tier from ratios:
    - Define `risk_score` (1–10) from a composite of leverage (D/E), interest coverage, liquidity (current & quick), earnings stability, FCF conversion.
    - Map to tier: Low (1–3), Medium (4–7), High (8–10).

- Margin of Safety (MoS) applied to `fair_value`:
    - Low risk: MoS = 10% → `suggestion_buy_price = fair_value * 0.90`
    - Medium risk: MoS = 20% → `suggestion_buy_price = fair_value * 0.80`
    - High risk: MoS = 30% → `suggestion_buy_price = fair_value * 0.70`

- Profit Target for `suggestion_sell_price`:
    - Low risk: +15% → `sell = fair_value * 1.15`
    - Medium risk: +20% → `sell = fair_value * 1.20`
    - High risk: +25% → `sell = fair_value * 1.25`

- Stop Loss:
    - Low risk: 8% below fair → `stop = fair_value * 0.92`
    - Medium risk: 12% → `stop = fair_value * 0.88`
    - High risk: 18% → `stop = fair_value * 0.82`

Null policy: If `fair_value` missing → all derived prices are `null`.

## 10. Fair vs Intrinsic Value Policy (Recommendation)

- Keep code-calculated `intrinsic_value` and `fair_value` for transparency, auditability, and consistency (they use reproducible formulas).
- Use AI to provide `suggestion_fair_value` only as a qualitative confirmation or adjustment range, NOT as the authoritative number.
- Deterministic rule:
    - If AI suggests a fair value, compare to code `fair_value`.
    - If delta ≤ 10%, accept code `fair_value`.
    - If delta > 10%, keep code `fair_value` but note AI range in `ai_response`; do not overwrite numeric field.

Rationale: Ratios feed into our valuation perception but authoritative numeric `fair_value` should remain code-driven to ensure repeatability. AI interprets context and highlights caveats.

## Questions for Your Review

1. **Ratio Priority**: Are these ratios comprehensive? Any missing?
2. **Margin of Safety**: Are 15% (buy), 20% (sell), 10% (stop loss) appropriate defaults?
3. **Composite Rating**: Should `suggestion_rating` be average of top 3 (moat, financials, valuation)?
4. **Missing Data**: Is using `null` acceptable, or prefer minimum threshold (e.g., "need 3+ years")?
5. **Prompt Tone**: Should AI be more quantitative (rules-based) or qualitative (analyst opinion)?


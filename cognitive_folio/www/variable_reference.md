{% raw %}
# AI Prompt Variable Reference

Unified variable syntax for Cognitive Folio AI prompts across Security, Portfolio, Holding, and Chat contexts.

---
## 1. Security Fields
Use double curly braces to inject fields from a `CF Security` document.

Example: `{{security_name}}`, `{{symbol}}`, `{{current_price}}`, `{{sector}}`

Rules:
- Dot path for JSON fields: `{{ticker_info.marketCap}}`
- Wildcard over arrays/dicts: `{{news.ARRAY.content.title}}` collects all titles.
- Index access: `{{news.0.content.title}}`

---
## 2. Holding Fields
Use double square brackets for `CF Portfolio Holding` fields when holding context exists.

Example: `[[quantity]]`, `[[average_purchase_price]]`, `[[current_value]]`, `[[allocation_percentage]]`

---
## 3. Portfolio Fields
Use double parentheses for `CF Portfolio` fields inside portfolio prompts.

Example: `((portfolio_name))`, `((risk_profile))`, `((total_value))`

---
## 4. Structured Financial Periods
Insert clean, formatted historical financial data using the periods syntax.

Pattern:
```
{{periods:<type>:<count>[:format]}}
```
- `<type>`: `annual`, `quarterly`, `ttm`
- `<count>`: number of periods (e.g. 3, 4, 5)
- `format` (optional): `markdown` (default), `text`, `json`, `table`

Examples:
- `{{periods:annual:3}}` → last 3 annual periods (markdown summary)
- `{{periods:quarterly:4:table}}` → last 4 quarters as a table
- `{{periods:annual:5:text}}` → plain text periods
- `{{periods:quarterly:8:json}}` → raw JSON (be mindful of token size)

Token Guidance:
- Annual 3 (markdown): ~200–400 tokens
- Quarterly 4 (table): ~250–500 tokens
- Annual 5 JSON: can exceed 800 tokens
Keep within model limits; prefer smaller counts for exploratory analysis.

---
## 5. Planned Extensions (Reserved Syntax)
Future additions (do not use yet):
- Comparisons: `((periods:compare:2024Q3:2024Q2))`
- Filtered ranges: `{{periods:annual:since:2021}}`
- Metric subset: `{{periods:metrics:revenue,net_income:annual:4:table}}`

---
## 6. JSON Path Extraction
When a field stores JSON (e.g. `news`, `ticker_info`):
- Single path: `{{ticker_info.marketCap}}`
- Array index: `{{news.0.content.title}}`
- Wildcard aggregation: `{{news.ARRAY.content.title}}`
  - Joins all non-empty values with comma separation.

---
## 7. File Attachments
Reference uploaded files in prompts with angle markers:
```
<<filename.pdf>>
```
Ensure the file is attached to the relevant document. Downstream parsing can extract and summarize if implemented.

---
## 8. Variable Collision & Fallback
If a variable cannot be resolved:
- Returns empty string for field paths
- Returns `[Error: ...]` for periods formatting failures
- JSON decode errors yield blank output

---
## 9. Best Practices
- Start with a concise context header (Security + latest periods)
- Use structured periods instead of dumping raw JSON blobs
- Avoid mixing large JSON (`{{periods:quarterly:8:json}}`) with verbose narrative requests
- Chain reasoning: supply data → ask specific analytical questions

Template Snippets:
```
Company Overview: {{security_name}} ({{symbol}}) Sector: {{sector}} Industry: {{industry}}
Latest Annual Performance:
{{periods:annual:3}}
Quarterly Trend:
{{periods:quarterly:4:table}}
Key News: {{news.ARRAY.content.title}}
```

---
## 10. Troubleshooting
| Issue | Cause | Action |
|-------|-------|--------|
| Empty periods block | No matching CF Financial Period records | Import financials first |
| `[Error: ...]` in output | Formatting or fetch failure | Re-check variable syntax |
| Huge token usage | Too many periods / JSON format | Reduce count or switch to `markdown` |
| Missing holding values | Holding context absent | Ensure prompt executed in portfolio holding loop |

---
## 11. Diff from Legacy
Legacy relied on raw blob fields (`profit_loss`, `balance_sheet`, `cash_flow`). New system uses normalized CF Financial Period records + computed metrics (margins, ROE, growth). Prefer `{{periods:...}}` going forward.

---
## 12. Quick Reference Cheat Sheet
| Type | Syntax | Example |
|------|--------|---------|
| Security Field | `{{field}}` | `{{current_price}}` |
| Holding Field | `[[field]]` | `[[quantity]]` |
| Portfolio Field | `((field))` | `((total_value))` |
| Financial Periods | `{{periods:type:count[:format]}}` | `{{periods:annual:3}}` |
| JSON Index | `{{jsonfield.0.key}}` | `{{news.0.content.title}}` |
| JSON Wildcard | `{{jsonfield.ARRAY.key}}` | `{{news.ARRAY.content.title}}` |
| Attachment | `<<file.pdf>>` | `<<q3_report.pdf>>` |

---
For updates watch release notes. Suggestions welcome.
{% endraw %}

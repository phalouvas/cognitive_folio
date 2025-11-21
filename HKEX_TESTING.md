# HKEX Testing Guide

## Overview

The HKEX (Hong Kong Stock Exchange) fetcher enables importing financial data from Hong Kong-listed companies using HKFRS (Hong Kong Financial Reporting Standards) XBRL filings.

**Supported Exchange:**
- HKG (Hong Kong Stock Exchange)

## Prerequisites

1. **Python dependencies installed:**
   ```bash
   cd /workspace/development/frappe-bench
   source env/bin/activate
   bench pip install python-xbrl requests
   ```

2. **HK stock code in symbol:**
   - Symbol format: `0700.HK`, `0005.HK`, etc.
   - System extracts stock code automatically (e.g., "0700" from "0700.HK")

## Current Implementation: Manual Upload Mode

HKEX doesn't provide a public API, so Phase 3 uses manual upload.

### How to Use

1. **Find the stock code:**
   - Example: Tencent = 0700, HSBC = 0005
   - Check symbol on CF Security

2. **Download HKFRS XBRL filing:**
   - Visit: https://www1.hkexnews.hk/search/titlesearch.xhtml
   - Enter stock code (e.g., "0700")
   - Select "Financial Statements/ESG Information"
   - Find "Annual Report" 
   - Download XBRL file (usually `.xhtml` or `.xml` extension)

3. **Upload to correct directory:**
   ```bash
   # Structure: sites/private/files/hkex/<stock_code>/Annual/<filing_date>/
   cd /workspace/development/frappe-bench/sites/kainotomo.localhost/private/files
   
   # Example for Tencent (stock code 0700)
   mkdir -p hkex/0700/Annual/2024-12-31
   
   # Copy your downloaded HKFRS file
   cp ~/Downloads/tencent_2024_hkfrs.xhtml hkex/0700/Annual/2024-12-31/report.xhtml
   ```

4. **Run the import:**
   ```bash
   bench --site kainotomo.localhost console
   ```
   
   In console:
   ```python
   import frappe
   from cognitive_folio.utils.hk_hkex_fetcher import fetch_hkex_financials
   
   # For a Hong Kong security
   result = fetch_hkex_financials('0700.HK')
   print(result)
   ```

5. **Or use auto-import:**
   - Open the CF Security for a Hong Kong stock
   - Ensure symbol format is like "0700.HK" (stock_exchange = HKG)
   - Click "Fetch Current Price" with fundamentals enabled
   - System will check for HKEX files and parse if available, otherwise fall back to Yahoo

## Verify Results

```bash
bench --site kainotomo.localhost console
```

```python
import frappe

# Check imported periods
periods = frappe.db.get_all(
    "CF Financial Period",
    filters={"security": "0700.HK", "data_source": "HKEX"},
    fields=["fiscal_year", "period_type", "data_quality_score", "total_revenue", "net_income"],
    order_by="fiscal_year desc"
)

for p in periods:
    print(f"{p.fiscal_year} {p.period_type}: Revenue={p.total_revenue}, Net Income={p.net_income}, Quality={p.data_quality_score}")
```

**Expected output:**
- `data_source = "HKEX"`
- `data_quality_score = 95`
- Financial metrics populated from HKFRS XBRL

## Common Hong Kong Stock Codes

| Company | Stock Code | Symbol |
|---------|------------|--------|
| Tencent Holdings | 0700 | 0700.HK |
| HSBC Holdings | 0005 | 0005.HK |
| AIA Group | 1299 | 1299.HK |
| China Mobile | 0941 | 0941.HK |
| Alibaba | 9988 | 9988.HK |
| Xiaomi | 1810 | 1810.HK |

## Finding HKFRS XBRL Files

### HKEXnews Portal

1. Visit: https://www1.hkexnews.hk/search/titlesearch.xhtml
2. Enter stock code (without .HK suffix)
3. Category: "Financial Statements/ESG Information"
4. Document Type: "Annual Report" or look for XBRL attachments
5. Download the XBRL file (look for .xhtml or .xml extensions)

### Tips:
- HKFRS filings are based on IFRS with Hong Kong modifications
- Not all annual reports include XBRL - look for newer filings (2020+)
- Some companies provide both PDF and XBRL versions
- XBRL files are often in a separate "Financials in XBRL" section

## Optional: Automated Download with Playwright

For bulk downloads, you can use the included Playwright helper:

```bash
# Install Playwright (optional)
bench pip install playwright
playwright install chromium
```

```python
import frappe
from pathlib import Path
from cognitive_folio.utils.hk_hkex_fetcher import download_hkex_with_playwright

# Download filings for stock code 0700
output_dir = Path(frappe.get_site_path("private", "files", "hkex", "0700", "Annual"))
output_dir.mkdir(parents=True, exist_ok=True)

success = download_hkex_with_playwright("0700", output_dir)
print(f"Download {'succeeded' if success else 'failed'}")
```

**Note:** Web scraping is fragile and may break if HKEXnews updates their site. Manual download is more reliable.

## Troubleshooting

**Issue: "HK stock code required"**
- Ensure symbol format is like "0700.HK" or "0005.HK"
- System extracts numeric code automatically
- Check `stock_exchange` field is set to "HKG"

**Issue: "No HKEX filings found"**
- Check directory path is correct
- Stock code should be numeric without .HK (e.g., "0700" not "0700.HK")
- Verify file is named `report.xhtml` or has `.xhtml`/`.xml` extension

**Issue: "No financial data extracted"**
- File may not be HKFRS XBRL format (check it's XBRL, not just PDF)
- Some older filings may not have XBRL versions
- Check frappe error logs for parsing details

**Issue: Falls back to Yahoo Finance**
- System will use Yahoo (quality 85) if no HKEX files found
- This is expected - upload HKFRS files to get quality 95

## Example: Tencent (0700)

1. Visit: https://www1.hkexnews.hk/search/titlesearch.xhtml
2. Search for stock code: `0700`
3. Filter by "Financial Statements"
4. Find latest Annual Report with XBRL attachment
5. Download the XBRL file
6. Place in: `sites/.../private/files/hkex/0700/Annual/2024-12-31/report.xhtml`
7. Run import via console or fetch fundamentals

## Phase 3 Coverage Summary

Your portfolio now has regulatory-quality (95 score) support for:
- ✅ US: SEC Edgar (NYQ, NMS)
- ✅ UK: Companies House (LSE, IOB)
- ✅ EU: ESEF manual upload (GER, PAR, AMS, MIL, MCE)
- ✅ Hong Kong: HKEX manual upload (HKG)

Remaining exchanges:
- EBS (Switzerland) - assess SIX e-Reporting
- PNK/OQX (US OTC) - limited filings, Yahoo fallback

## See Also

- `PHASE3_IMPLEMENTATION.md` - Detailed implementation overview
- `DEPLOYMENT.md` - Overall deployment and phase status
- `EU_ESEF_TESTING.md` - Similar guide for European exchanges
- `cognitive_folio/utils/hk_hkex_fetcher.py` - Implementation code
- `cognitive_folio/utils/taxonomy_mapper.py` - HKFRS concept mapping

# EU ESEF Testing Guide

## Overview

The EU ESEF (European Single Electronic Format) fetcher enables importing financial data from major European exchanges using XBRL/iXBRL filings in IFRS format.

**Supported Exchanges:**
- GER (Germany: Xetra/Frankfurt)
- PAR (Euronext Paris, France)
- AMS (Euronext Amsterdam, Netherlands)
- MIL (Euronext Milan, Italy)
- MCE (Madrid, Spain)

## Prerequisites

1. **Python dependencies installed:**
   ```bash
   cd /workspace/development/frappe-bench
   source env/bin/activate
   bench pip install python-xbrl requests
   ```

2. **ISIN required:**
   - EU securities must have their ISIN populated on CF Security
   - Example: DE0005140008 (Deutsche Bank), FR0000120271 (TotalEnergies)

## Current Implementation: Manual Upload Mode

Phase 3 MVP uses a manual upload approach because:
- Each EU country has its own regulator with different APIs
- No unified ESMA API available yet
- Requires country-specific authentication/registration

### How to Use

1. **Find the ESEF filing:**
   - Germany: https://www.bundesanzeiger.de
   - France: https://www.amf-france.org
   - Netherlands: https://www.afm.nl
   - Italy: https://www.consob.it
   - Spain: https://www.cnmv.es

2. **Download the ESEF XHTML file:**
   - Look for "Annual Financial Report" or "ESEF" filings
   - Download the `.xhtml` or `.xml` file (iXBRL format)

3. **Upload to correct directory:**
   ```bash
   # Structure: sites/private/files/eu_esef/<ISIN>/Annual/<filing_date>/
   cd /workspace/development/frappe-bench/sites/kainotomo.localhost/private/files
   
   # Example for Deutsche Bank (ISIN: DE0005140008)
   mkdir -p eu_esef/DE0005140008/Annual/2024-12-31
   
   # Copy your downloaded ESEF file
   cp ~/Downloads/deutsche_bank_2024_esef.xhtml eu_esef/DE0005140008/Annual/2024-12-31/report.xhtml
   ```

4. **Run the import:**
   ```bash
   bench --site kainotomo.localhost console
   ```
   
   In console:
   ```python
   import frappe
   from cognitive_folio.utils.eu_esef_fetcher import fetch_eu_esef_financials
   
   # For a German security
   result = fetch_eu_esef_financials('DBK.DE')
   print(result)
   ```

5. **Or use auto-import:**
   - Open the CF Security for a European stock
   - Ensure ISIN is set
   - Ensure stock_exchange is one of: GER, PAR, AMS, MIL, MCE
   - Click "Fetch Current Price" with fundamentals enabled
   - System will check for ESEF files and parse if available, otherwise fall back to Yahoo

## Verify Results

```bash
bench --site kainotomo.localhost console
```

```python
import frappe

# Check imported periods
periods = frappe.db.get_all(
    "CF Financial Period",
    filters={"security": "DBK.DE", "data_source": "EU ESEF"},
    fields=["fiscal_year", "period_type", "data_quality_score", "total_revenue", "net_income"],
    order_by="fiscal_year desc"
)

for p in periods:
    print(f"{p.fiscal_year} {p.period_type}: Revenue={p.total_revenue}, Net Income={p.net_income}, Quality={p.data_quality_score}")
```

**Expected output:**
- `data_source = "EU ESEF"`
- `data_quality_score = 95`
- Financial metrics populated from XBRL

## Finding ISINs

If ISIN is missing on your securities:

```python
import frappe

# Find EU securities without ISIN
eu_exchanges = ['GER', 'PAR', 'AMS', 'MIL', 'MCE']
securities = frappe.db.get_all(
    "CF Security",
    filters={
        "stock_exchange": ["in", eu_exchanges],
        "isin": ["is", "not set"]
    },
    fields=["name", "security_name", "stock_exchange"]
)

print(f"Found {len(securities)} EU securities without ISIN:")
for s in securities:
    print(f"{s.name} - {s.security_name} ({s.stock_exchange})")
```

ISINs can be found:
- Yahoo Finance page for the stock
- Company investor relations website
- National stock exchange website

## Future Enhancement: Direct API Integration

Future versions will implement direct downloads from:
- Germany: Bundesanzeiger API (requires registration)
- France: AMF ESMA-compliant API
- Netherlands: AFM OAM
- Italy: CONSOB public search
- Spain: CNMV transparency portal

This will eliminate the manual upload step.

## Troubleshooting

**Issue: "No ESEF filings found"**
- Check the directory path is correct
- Ensure ISIN matches exactly
- Verify file is named `report.xhtml` or has `.xhtml`/`.xml` extension

**Issue: "No financial data extracted"**
- File may not be proper ESEF format (check it's XBRL/iXBRL)
- Some older filings may use non-standard taxonomies
- Check frappe error logs for parsing details

**Issue: Falls back to Yahoo Finance**
- System will use Yahoo (quality 85) if no ESEF files found
- This is expected behavior - upload ESEF files to get quality 95

## Example: Deutsche Bank

1. Visit: https://www.bundesanzeiger.de
2. Search for "Deutsche Bank AG" (or register number HRB 30000)
3. Find "Jahresabschluss" (Annual Report) for latest year
4. Download the ESEF iXBRL file
5. Place in: `sites/.../private/files/eu_esef/DE0005140008/Annual/2024-12-31/report.xhtml`
6. Run import via console or fetch fundamentals

## See Also

- `PHASE3_IMPLEMENTATION.md` - Detailed API research and future plans
- `DEPLOYMENT.md` - Overall deployment and phase status
- `cognitive_folio/utils/eu_esef_fetcher.py` - Implementation code
- `cognitive_folio/utils/taxonomy_mapper.py` - IFRS concept mapping

# Cognitive Folio Deployment Guide

## Overview

This document describes the deployment requirements and phased rollout strategy for the Cognitive Folio financial data fetching system.

## Current Implementation (Phase 1 & 2)

### Required Libraries

The following Python libraries are **currently required** and must be installed in production:

```bash
# Phase 1 - Yahoo Finance (Required for all)
pip install yfinance openai

# Phase 2 - SEC Edgar (Optional, for US companies - COMPLETED)
pip install sec-edgar-downloader python-xbrl lxml pdfplumber
```

Or add to `requirements.txt` / `pyproject.toml`:

```txt
# Phase 1 - Required
yfinance>=0.2.0
openai>=1.0.0

# Phase 2 - Optional (US companies - COMPLETED)
sec-edgar-downloader>=5.0.0
python-xbrl>=2.1.0
lxml>=4.9.0
pdfplumber>=0.9.0
```

### Features Available

Phase 1 provides:

- **Yahoo Finance Integration**: Automatic financial data fetching for all supported stock exchanges worldwide
- **SEC CIK Lookup**: Automatic retrieval and caching of SEC Central Index Keys for US-listed companies
- **Auto-Upgrade Logic**: Intelligent data quality comparison - automatically upgrades financial periods when better quality data becomes available
- **Unified Workflow**: Single "Fetch Fundamentals" button fetches both price data AND creates structured financial periods
- **Data Quality Scoring**: Transparent quality scores (Yahoo Finance: 85, PDF/SEC Edgar: 95, Manual Entry: 100)

### Data Sources

- **Primary**: Yahoo Finance (Quality Score: 85)
  - Covers most major global stock exchanges
  - Includes Income Statement, Balance Sheet, and Cash Flow data
  - Both Annual and Quarterly periods
- **Secondary**: Manual entry (Quality Score: 100) and PDF upload (Quality Score: 95) still available for specialized needs

### No Backward Compatibility

⚠️ **Important**: Phase 1 deliberately **removes backward compatibility** with the old two-step workflow:

- **REMOVED**: "Import to Financial Periods" button (replaced by inline import during "Fetch Fundamentals")
- **REMOVED**: "Upload Financial Statement" button (PDF parsing kept as library function only)
- **REMOVED**: `import_from_yahoo_finance()` whitelisted function from `cf_financial_period.py`
- **REMOVED**: `upload_and_parse_financial_pdf()` whitelisted function from `pdf_financial_parser.py`

This simplifies the user experience and reduces confusion.

### Caching Strategy

- **SEC CIK Mappings**: Cached for 24 hours using Frappe cache
- **API Endpoint**: `https://www.sec.gov/files/company_tickers.json`
- **User-Agent Required**: "Cognitive Folio Financial App (compliance@example.com)" header sent with all SEC requests

## Future Implementation (Phase 2+)

### Planned Libraries

Phase 2 will introduce **optional** XBRL parsing capabilities for higher-quality data from regulatory filings:

```bash
# Phase 2 - SEC Edgar (United States) - COMPLETED ✅
pip install sec-edgar-downloader>=5.0.0

# Phase 2 - Inline XBRL Parsing
pip install python-xbrl>=2.1.0 lxml>=4.9.0

# Phase 2 - Enhanced PDF fallback
pip install pdfplumber>=0.9.0 PyPDF2>=3.0.0

# Note: Using python-xbrl for inline XBRL (iXBRL) files from SEC Edgar
# SEC filings use iXBRL embedded in HTML, not standalone XBRL XML
# python-xbrl provides better BeautifulSoup-based parsing vs ixbrl-parse
```

### Planned Data Sources

Phase 2+ will add support for regulatory filings from major stock exchanges:

| Region | Exchange | Data Source | Quality Score | Standard | Status |
|--------|----------|-------------|---------------|----------|--------|
| 🇺🇸 United States | SEC Edgar | XBRL/iXBRL | 95 | US-GAAP | ✅ Complete |
| 🇬🇧 United Kingdom | Companies House | iXBRL | 95 | UK-GAAP | ✅ Phase 3 |
| 🇪🇺 European Union | ESEF (GER/PAR/AMS/MIL/MCE) | XBRL | 95 | ESEF (IFRS) | ✅ Phase 3 |
| 🇭🇰 Hong Kong | HKEX | XBRL/iXBRL | 95 | HKFRS | ✅ Phase 3 |
| 🇨🇭 Switzerland | SIX | XBRL | 95 | IFRS/Swiss GAAP | ✅ Phase 3 |
| 🇨🇦 Canada | SEDAR+ | XBRL | 95 | IFRS/CA-GAAP | Phase 4 |
| 🇯🇵 Japan | EDINET | XBRL | 95 | JGAAP | Phase 4 |
| 🇦🇺 Australia | ASIC | XBRL | 95 | AIFRS | Phase 4 |
| 🇨🇳 China | CSRC | XBRL | 95 | CAS | Phase 4 |
| 🌍 Fallback | Yahoo Finance | JSON | 85 | Proprietary | Current ✅ |

### XBRL Taxonomy Considerations

Different regions use different XBRL taxonomies for the same financial concepts:

- **US-GAAP** (United States): `us-gaap:Revenues`, `us-gaap:NetIncomeLoss`
- **IFRS** (International/EU): `ifrs-full:Revenue`, `ifrs-full:ProfitLoss`
- **ESEF** (EU Securities): iXBRL format with IFRS taxonomy
- **UK-GAAP** (United Kingdom): `uk-gaap:TurnoverRevenue`, `uk-gaap:ProfitLossForPeriod`
- **CAS** (China mainland): Chinese Accounting Standards taxonomy
- **HKFRS** (Hong Kong): Hong Kong Financial Reporting Standards

Phase 2 will implement taxonomy mapping logic to normalize these into our standard field names.

## Phased Rollout Strategy

### Phase 1: Yahoo Finance (Current) ✅

**Goal**: Simplify UX, consolidate workflow, prepare infrastructure

**Changes**:
- Add `sec_cik` field to CF Security
- Implement inline financial period creation during "Fetch Fundamentals"
- Remove duplicate buttons and separate import step
- Auto-upgrade existing periods when quality improves
- No new library dependencies

**Benefits**:
- Immediate UX improvement
- ~85% accuracy for most global exchanges
- No additional infrastructure requirements

### Phase 2: SEC Edgar (United States) ✅ COMPLETED

**Goal**: Achieve 95%+ accuracy for US-listed companies

**Changes** (FULLY IMPLEMENTED):
- ✅ Added `sec-edgar-downloader` library (v5.0.3)
- ✅ Added `python-xbrl` library for inline XBRL parsing (replaces ixbrl-parse)
- ✅ Implemented SEC Edgar file download infrastructure
- ✅ Auto-downloads SEC filings when `sec_cik` field is populated
- ✅ Complete XBRL fact extraction with US-GAAP concept mapping (40+ fields)
- ✅ Intelligent upgrade logic: SEC (95) > PDF (95) > Yahoo (85)
- ✅ Fallback to Yahoo Finance for non-US or when SEC parsing fails
  
**Current Status** (as of Nov 2025):
- SEC Edgar integration fully operational
- Downloads 10-K and 10-Q filings to `private/files/sec_edgar/sec-edgar-filings/{CIK}/`
- Extracts financial data from inline XBRL HTML using python-xbrl parser
- Maps US-GAAP taxonomy to CF Financial Period fields:
  - Income Statement: Revenue, COGS, Gross Profit, Operating Income, Net Income, EPS
  - Balance Sheet: Assets, Liabilities, Equity, Cash, Receivables, Inventory, Debt
  - Cash Flow: Operating, Investing, Financing, CapEx, Free Cash Flow
- Creates/upgrades CF Financial Period documents with quality score 95
- Handles both annual (10-K) and quarterly (10-Q) filings
- Respects override_yahoo flag to prevent unwanted updates

**How to Verify SEC Edgar is Working**:
```bash
# Check if files are being downloaded
ls -la sites/yoursite.com/private/files/sec_edgar/sec-edgar-filings/

# For AAPL (CIK 0000320193):
ls -la sites/yoursite.com/private/files/sec_edgar/sec-edgar-filings/0000320193/10-K/
ls -la sites/yoursite.com/private/files/sec_edgar/sec-edgar-filings/0000320193/10-Q/

# In Frappe console:
import frappe
from cognitive_folio.utils.sec_edgar_fetcher import fetch_sec_edgar_financials
result = fetch_sec_edgar_financials('AAPL', '0000320193')
print(result)  # Check imported/upgraded counts

# Verify quality scores
periods = frappe.db.sql("""
    SELECT fiscal_year, fiscal_quarter, data_quality_score, data_source
    FROM `tabCF Financial Period`
    WHERE security='AAPL' AND data_source='SEC Edgar'
    ORDER BY fiscal_year DESC, fiscal_quarter DESC
    LIMIT 5
""", as_dict=True)
for p in periods:
    print(p)
```

Note: There is only one user action "Fetch Fundamentals". The app automatically tries SEC Edgar first for US companies, then falls back to Yahoo Finance. No separate button is presented.

**Benefits**:
- ✅ 95% accuracy for US companies from regulatory filings
- ✅ Regulatory-quality data directly from SEC Edgar
- ✅ Automatic source selection (SEC Edgar → Yahoo Finance fallback)
- ✅ Intelligent auto-upgrade: replaces Yahoo data (85) with SEC data (95)
- ✅ Support for both annual (10-K) and quarterly (10-Q) periods
- ✅ Derived metrics calculated automatically (gross profit, free cash flow)

### Phase 3: Major Global Exchanges 🚧 IN PROGRESS

**Goal**: Extend 95%+ accuracy to Hong Kong, UK, EU, Canada, Japan, Australia

**Architecture** (COMPLETED):
- ✅ **Taxonomy Mapper** (`taxonomy_mapper.py`): Maps XBRL concepts from IFRS, UK-GAAP, HKFRS, ESEF, JGAAP, AIFRS to CF fields
- ✅ **Base XBRL Fetcher** (`base_xbrl_fetcher.py`): Abstract class providing common XBRL parsing, context extraction, period creation
- ✅ **Auto-taxonomy Detection**: Detects accounting standard from XBRL namespaces
- ✅ **Regional Fetcher Framework**: Exchange-specific fetchers inherit from base class

**Targeted Exchanges (based on current database):**
- UK: `LSE`, `IOB` → Companies House API (iXBRL) ✅ High Priority
- EU: `GER`, `PAR`, `AMS`, `MIL`, `MCE` → ESEF/IFRS via national regulators ✅ High Priority
- Hong Kong: `HKG` → HKEXnews (scraping) ⚠️ Medium Priority
- Switzerland: `EBS` → SIX OAM/e-Reporting (assess) ⚠️ Medium Priority
- US OTC: `PNK`, `OQX` → Limited filings; default to Yahoo ⚠️ Low Priority
- US: `NYQ`, `NMS` → SEC Edgar ✅ Already implemented (Phase 2)

**Implementation Status**:
- ✅ Foundation complete (taxonomy mapper, base fetcher framework)
- ✅ UK Companies House fetcher (`uk_companies_house_fetcher.py`) - FREE API
  - Auto-routes for LSE/IOB exchanges when `companies_house_number` is set
  - Downloads iXBRL accounts via Companies House Document API
  - Quality score: 95
  - Setup: Register for free API key, add `companies_house_api_key` to site config
- ✅ EU ESEF fetcher (`eu_esef_fetcher.py`) - Manual upload mode
  - Supports GER, PAR, AMS, MIL, MCE exchanges
  - Parses ESEF XHTML/XML with IFRS taxonomy
  - Quality score: 95
  - Requires ISIN on security
  - Manual upload to: `sites/private/files/eu_esef/<ISIN>/Annual/<date>/report.xhtml`
  - Future: Direct API integration with national regulators
- ✅ Hong Kong HKEX fetcher (`hk_hkex_fetcher.py`) - Manual upload mode
  - Auto-routes for HKG exchange
  - Parses HKFRS XBRL with IFRS/HKFRS taxonomy
  - Quality score: 95
  - Stock code extracted from symbol (e.g., "0700.HK" → "0700")
  - Manual upload to: `sites/private/files/hkex/<stock_code>/Annual/<date>/report.xhtml`
  - Optional: Playwright automation script included
- ✅ Switzerland SIX Swiss Exchange fetcher (`ch_six_fetcher.py`) - Manual upload mode
  - Auto-routes for EBS exchange
  - Parses Swiss XBRL with IFRS/Swiss GAAP FER taxonomy
  - Quality score: 95
  - Requires Swiss ISIN (CH + 10 digits, e.g., CH0038863350)
  - Manual upload to: `sites/private/files/six/<ISIN>/Annual/<date>/report.xhtml`
  - Covers: NESN.SW (Nestlé), ROG.SW (Roche)
- ⏳ US OTC (fallback to Yahoo, optional OTC Markets paid API)
- ⏳ Canada SEDAR+ (strategic, not yet in DB)

**See**: `PHASE3_IMPLEMENTATION.md` for detailed API research, priorities, and technical requirements

**Benefits** (when complete):
- Consistent 95% quality data across major markets
- Reduced reliance on Yahoo Finance for international stocks
- Support for 7+ regional accounting standards (US-GAAP, IFRS, UK-GAAP, HKFRS, etc.)

### Phase 4: Emerging Markets

**Goal**: China, India, Brazil, and other emerging markets

**Changes**:
- Support for region-specific taxonomies (CAS for China, IndAS for India, etc.)
- Enhanced fallback mechanisms for markets without structured data
- Multi-language support for financial statements

## Deployment Commands

### Development Environment

```bash
# Navigate to Frappe bench
cd /path/to/frappe-bench

# Install Python dependencies (Phase 1 only)
./env/bin/pip install yfinance openai

# Update Cognitive Folio app
bench update --apps cognitive_folio

# Migrate database (adds sec_cik field)
bench migrate

# Clear cache (recommended after upgrade)
bench clear-cache

# Restart processes
bench restart
```

### Production Environment

```bash
# Install dependencies
sudo -u frappe /path/to/frappe-bench/env/bin/pip install yfinance openai

# Update app
cd /path/to/frappe-bench/apps/cognitive_folio
git pull origin main

# Migrate database
cd /path/to/frappe-bench
sudo -u frappe bench migrate --site your-site.com

# Clear cache
sudo -u frappe bench clear-cache --site your-site.com

# Restart services
sudo systemctl restart frappe-bench-web.service
sudo systemctl restart frappe-bench-worker.service
sudo systemctl restart frappe-bench-schedule.service
```

## Configuration

### Frappe Cache Configuration

Ensure Redis is properly configured for caching (typically already configured in Frappe):

```python
# site_config.json (usually no changes needed)
{
  "redis_cache": "redis://localhost:13000"
}
```

### SEC API Compliance

The system sends a compliant User-Agent header with SEC API requests:

```
User-Agent: Cognitive Folio Financial App (compliance@example.com)
```

Replace the email address in `cf_security.py` line ~151 if needed:

```python
headers = {
    'User-Agent': 'Cognitive Folio Financial App (your-compliance-email@example.com)'
}
```

## Monitoring

### Check Financial Period Import Status

```python
# In Frappe console (bench console)
doc = frappe.get_doc("CF Security", "AAPL")
if doc.last_period_import_result:
    import json
    result = json.loads(doc.last_period_import_result)
    print(f"Imported: {result['imported_count']}")
    print(f"Updated: {result['updated_count']}")
    print(f"Upgraded: {result['upgraded_count']}")
    print(f"Skipped: {result['skipped_count']}")
```

### Check SEC CIK Cache

```python
# Check cached CIK
cache_key = "sec_cik:AAPL"
cik = frappe.cache().get(cache_key)
print(f"AAPL CIK: {cik}")
```

## Troubleshooting

### Issue: Financial periods not being created

**Solution**: Check CF Settings → "Auto Import Financial Periods" is enabled (default: enabled)

### Issue: SEC CIK not being populated

**Solution**: Verify internet connectivity to `https://www.sec.gov/files/company_tickers.json`

### Issue: Yahoo Finance data quality lower than expected

**Solution**: Phase 1 is designed for convenience. For higher quality (95%+), wait for Phase 2 SEC Edgar integration.

### Issue: Upgrade notifications not showing

**Solution**: Check `last_period_import_result` field in CF Security document for detailed results.

## Support

For issues or questions:

1. Check Frappe error logs: `frappe-bench/logs/`
2. Review import results in `last_period_import_result` field
3. Verify dependencies: `bench pip freeze | grep -E "(yfinance|openai)"`

## License

See `license.txt` in the app root directory.

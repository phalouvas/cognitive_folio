# Cognitive Folio Deployment Guide

## Overview

This document describes the deployment requirements and phased rollout strategy for the Cognitive Folio financial data fetching system.

## Current Implementation (Phase 1 & 2)

### Required Libraries

The following Python libraries are **currently required** and must be installed in production:

```bash
# Phase 1 - Yahoo Finance (Required for all)
pip install yfinance openai

# Phase 2 - SEC Edgar (Optional, for US companies - IN PROGRESS)
pip install sec-edgar-downloader ixbrl-parse lxml pdfplumber
```

Or add to `requirements.txt` / `pyproject.toml`:

```txt
# Phase 1 - Required
yfinance>=0.2.0
openai>=1.0.0

# Phase 2 - Optional (US companies - IN PROGRESS)
sec-edgar-downloader>=5.0.0
ixbrl-parse>=0.10.0
lxml>=4.9.0
pdfplumber>=0.9.0
```

### Features Available

Phase 1 provides:

- **Yahoo Finance Integration**: Automatic financial data fetching for all supported stock exchanges worldwide
- **SEC CIK Lookup**: Automatic retrieval and caching of SEC Central Index Keys for US-listed companies
- **Auto-Upgrade Logic**: Intelligent data quality comparison - automatically upgrades financial periods when better quality data becomes available
- **Unified Workflow**: Single "Fetch Fundamentals" button fetches both price data AND creates structured financial periods
- **Data Quality Scoring**: Transparent quality scores (Yahoo Finance: 85, PDF Upload: 90, Manual Entry: 100)

### Data Sources

- **Primary**: Yahoo Finance (Quality Score: 85)
  - Covers most major global stock exchanges
  - Includes Income Statement, Balance Sheet, and Cash Flow data
  - Both Annual and Quarterly periods
- **Secondary**: Manual entry (Quality Score: 100) and PDF upload (Quality Score: 90) still available for specialized needs

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
# Phase 2 - SEC Edgar (United States) - IN PROGRESS
pip install sec-edgar-downloader>=5.0.0

# Phase 2 - Inline XBRL Parsing
pip install ixbrl-parse>=0.10.0 lxml>=4.9.0

# Phase 2 - Enhanced PDF fallback
pip install pdfplumber>=0.9.0 PyPDF2>=3.0.0

# Note: Using ixbrl-parse for inline XBRL (iXBRL) files from SEC Edgar
# SEC filings use iXBRL embedded in HTML, not standalone XBRL XML
```

### Planned Data Sources

Phase 2+ will add support for regulatory filings from major stock exchanges:

| Region | Exchange | Data Source | Quality Score | Standard | Status |
|--------|----------|-------------|---------------|----------|--------|
| 🇺🇸 United States | SEC Edgar | XBRL/iXBRL | 95 | US-GAAP | Phase 2 |
| 🇭🇰 Hong Kong | HKEX | XBRL/iXBRL | 95 | HKFRS | Phase 2 |
| 🇬🇧 United Kingdom | Companies House | iXBRL | 95 | UK-GAAP | Phase 2 |
| 🇪🇺 European Union | ESEF Portal | XBRL | 95 | ESEF (IFRS) | Phase 3 |
| 🇨🇦 Canada | SEDAR+ | XBRL | 95 | IFRS/CA-GAAP | Phase 3 |
| 🇯🇵 Japan | EDINET | XBRL | 95 | JGAAP | Phase 3 |
| 🇦🇺 Australia | ASIC | XBRL | 95 | AIFRS | Phase 3 |
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

### Phase 2: SEC Edgar (United States) 🚧 IN PROGRESS

**Goal**: Achieve 95%+ accuracy for US-listed companies

**Changes** (PARTIALLY IMPLEMENTED):
- ✅ Added `sec-edgar-downloader` library (v5.0.3)
- ✅ Added `ixbrl-parse` library (v0.10.1) for inline XBRL parsing
- ✅ Implemented SEC Edgar file download infrastructure
- ✅ Auto-downloads SEC filings when `sec_cik` field is populated
- ⏳ XBRL fact extraction **NOT YET COMPLETE** - currently falls back to Yahoo Finance
- ✅ Fallback to Yahoo Finance working correctly
  
**Current Status** (as of Nov 2025):
- SEC Edgar integration downloads 10-K and 10-Q filings successfully
- Files are saved to `private/files/sec_edgar/sec-edgar-filings/{CIK}/`
- XBRL parsing infrastructure is in place but fact extraction needs completion
- **Currently using Yahoo Finance** for actual data until XBRL parsing is complete

**How to Verify SEC Edgar is Working**:
```bash
# Check if files are being downloaded
ls -la sites/yoursite.com/private/files/sec_edgar/sec-edgar-filings/

# For AAPL (CIK 0000320193):
ls -la sites/yoursite.com/private/files/sec_edgar/sec-edgar-filings/0000320193/10-K/
ls -la sites/yoursite.com/private/files/sec_edgar/sec-edgar-filings/0000320193/10-Q/
```

Note: There is only one user action "Fetch Fundamentals". The app automatically tries SEC Edgar first for US companies, then falls back to Yahoo Finance. No separate button is presented.

**Pending Work**:
- Complete XBRL fact extraction from XbrlInstance objects
- Map US-GAAP concepts to CF Financial Period fields
- Handle different fiscal period variations

**Benefits** (when complete):
- 95%+ accuracy for US companies
- Regulatory-quality data from official SEC filings
- Automatic source selection (SEC Edgar → Yahoo Finance fallback)
- Intelligent auto-upgrade: replaces Yahoo data (85) with SEC data (95)

### Phase 3: Major Global Exchanges

**Goal**: Extend 95%+ accuracy to Hong Kong, UK, EU, Canada, Japan, Australia

**Changes**:
- Extend XBRL parser to support IFRS, UK-GAAP, HKFRS, ESEF taxonomies
- Implement exchange-specific downloaders (HKEX API, Companies House API, etc.)
- Add taxonomy mapping layer

**Benefits**:
- Consistent high-quality data across major markets
- Reduced reliance on Yahoo Finance

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

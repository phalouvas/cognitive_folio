# Phase 3 Implementation Guide

## Overview

Phase 3 extends financial data fetching to major global stock exchanges beyond the US, covering Hong Kong, UK, EU, Canada, Japan, and Australia. This document outlines the implementation strategy, API research findings, and technical requirements.

## Current Portfolio Exchanges (from database)

Detected stock exchanges in the current dataset (13 total):

- NYQ (NYSE, US)
- NMS (Nasdaq, US)
- GER (Germany: Xetra/Frankfurt)
- PAR (Euronext Paris, France)
- HKG (Hong Kong: HKEX)
- AMS (Euronext Amsterdam, Netherlands)
- MCE (Madrid, Spain: BME)
- MIL (Euronext Milan, Italy)
- LSE (London Stock Exchange, UK)
- EBS (SIX Swiss Exchange, Switzerland)
- PNK (US OTC Pink)
- OQX (US OTCQX)
- IOB (LSE International Order Book, UK)

Implications for Phase 3 scope:

- Covered already: NYQ/NMS via SEC Edgar (Phase 2 ✅)
- High priority to implement next: LSE/IOB (UK Companies House), EU markets (GER, PAR, AMS, MIL, MCE) via ESEF/IFRS
- Medium priority: HKG (HKEX)
- Assess/Defer: EBS (Switzerland, SIX), US OTC (PNK/OQX) – likely fallback to Yahoo unless paid APIs are used

## Architecture

### Core Components

1. **Taxonomy Mapper** (`taxonomy_mapper.py`)
   - Maps XBRL concepts from different accounting standards to CF Financial Period fields
   - Supports: US-GAAP, IFRS, ESEF, UK-GAAP, HKFRS, CA-GAAP, JGAAP, AIFRS
   - Auto-detects taxonomy from XBRL namespaces
   - Provides flexible concept matching (with/without prefixes, case-insensitive)

2. **Base XBRL Fetcher** (`base_xbrl_fetcher.py`)
   - Abstract base class for all regional fetchers
   - Handles common XBRL parsing, context extraction, period creation
   - Subclasses only implement exchange-specific downloading and identifier logic
   - Consistent error handling and reporting

3. **Regional Fetchers** (to be implemented)
   - Each exchange gets its own fetcher class inheriting from `BaseXBRLFetcher`
   - Example: `hk_hkex_fetcher.py`, `uk_companies_house_fetcher.py`

### Data Flow

```
CF Security 
    ↓
Exchange Detection (stock_exchange field + ticker pattern)
    ↓
Regional Fetcher (inherits BaseXBRLFetcher)
    ↓
Download XBRL filings from exchange
    ↓
Parse XBRL → Extract namespaces → Detect Taxonomy
    ↓
Taxonomy Mapper (map concepts to CF fields)
    ↓
Create/Update CF Financial Period (quality score 95)
```

## Exchange-Specific Research

### 🇭🇰 Hong Kong (HKEX)

**Status**: ✅ IMPLEMENTED (Manual Upload Mode)  
**Priority**: HIGH (major Asian market)

**Data Source**: HKEXnews (https://www1.hkexnews.hk)

**Key Findings**:
- **No Public API**: HKEX does not provide a public REST API for programmatic access
- **Web Portal Only**: Financial statements available through HKEXnews web portal
- **XBRL Format**: Companies file in XBRL format (HKFRS taxonomy based on IFRS)
- **Access Method**: Manual download or optional web automation
- **Search Interface**: https://www1.hkexnews.hk/search/titlesearch.xhtml

**Implementation**: `hk_hkex_fetcher.py`
- Inherits from `BaseXBRLFetcher`
- **Current Mode**: Manual file upload with structured directory guidance
- Parses HKFRS XBRL using IFRS/HKFRS taxonomy mapper
- Maps to CF Financial Period with quality score 95
- Auto-routes for stock_exchange = HKG
- Requires HK stock code (e.g., "0700", "0005") - extracted from symbol like "0700.HK"

**Directory Structure** (manual upload):
```
sites/private/files/hkex/<stock_code>/Annual/<YYYY-MM-DD>/
  report.xhtml (or .xml)
```

**Search Instructions**:
1. Visit: https://www1.hkexnews.hk/search/titlesearch.xhtml
2. Enter stock code (e.g., "0700" for Tencent)
3. Select "Financial Statements/ESG Information"
4. Download XBRL/iXBRL file from Annual Report
5. Place in structured directory

**Future Enhancement**: Optional Playwright automation script included (requires: `pip install playwright`)

---

### 🇬🇧 United Kingdom (Companies House)

**Status**: ✅ IMPLEMENTED  
**Priority**: HIGH (well-documented API)

**Data Source**: Companies House API (https://developer.company-information.service.gov.uk/)

**Key Findings**:
- **Public API Available**: Free REST API with API key authentication
- **iXBRL Format**: Companies file accounts in iXBRL (inline XBRL in HTML)
- **UK-GAAP Taxonomy**: Uses UK-GAAP for smaller companies, IFRS for larger companies
- **Rate Limits**: 600 requests per 5 minutes
- **Document Downloads**: Separate document API for filing downloads

**API Endpoints**:
```
Search Company: GET /search/companies?q={name}
Company Profile: GET /company/{company_number}
Filing History: GET /company/{company_number}/filing-history
Document Download: GET /document/{document_id}/content
```

**Authentication**: API key required (free registration at https://developer.company-information.service.gov.uk/)

**Implementation**: `uk_companies_house_fetcher.py`
- Inherits from `BaseXBRLFetcher`
- Fetches filing history via Companies House API
- Downloads iXBRL accounts (prefers application/xhtml+xml, text/html, application/xml)
- Maps to CF Financial Period with quality score 95
- Requires `companies_house_number` field set on CF Security
- Auto-routes for stock_exchange = LSE or IOB

**Setup Required**:
1. Register for free API key at Companies House developer portal
2. Add `companies_house_api_key` to site config
3. Set `companies_house_number` on UK securities (e.g., "00445790" for Tesco)

---

### 🇪🇺 European Union (ESEF Portal)

**Status**: ✅ IMPLEMENTED (Manual Upload Mode)  
**Priority**: HIGH (covers GER, PAR, AMS, MIL, MCE exchanges)

**Data Source**: ESMA FIRDS / National Competent Authorities

**Key Findings**:
- **No Central API**: ESEF filings distributed across national regulators
- **ESEF Format**: Inline XBRL with IFRS taxonomy
- **Mandatory Since 2021**: All EU-listed companies must file in ESEF format
- **Access Points**: Each country has own regulator (BaFin, AMF, CONSOB, etc.)
- **ESMA Database**: European Single Access Point (ESAP) planned but not fully operational

**Implementation Challenges**:
- 27 different national authorities with different access methods
- No unified API or search interface
- Language barriers (filings in local languages)
- Varying rate limits and authentication requirements

**Implementation**: `eu_esef_fetcher.py`
- Inherits from `BaseXBRLFetcher`
- **Current Mode**: Manual file upload with structured directory guidance
- Supports exchanges: GER (Germany), PAR (France), AMS (Netherlands), MIL (Italy), MCE (Spain)
- Parses ESEF XHTML/XML using IFRS taxonomy mapper
- Maps to CF Financial Period with quality score 95
- Requires ISIN for identification

**Directory Structure** (manual upload):
```
sites/private/files/eu_esef/<ISIN>/Annual/<YYYY-MM-DD>/
  report.xhtml (or .xml)
```

**National Regulator Sources**:
- Germany: https://www.bundesanzeiger.de
- France: https://www.amf-france.org
- Netherlands: https://www.afm.nl
- Italy: https://www.consob.it
- Spain: https://www.cnmv.es

**Future Enhancement**: Direct API integration with national regulators (requires country-specific authentication)

**Auto-routing**: Activates for stock_exchange in [GER, PAR, AMS, MIL, MCE] when ISIN is set

---

### 🇨🇭 Switzerland (SIX Swiss Exchange)

**Status**: ✅ IMPLEMENTED (Manual Upload Mode)  
**Priority**: MEDIUM (2 securities in portfolio)

**Data Source**: SIX Exchange Regulation - e-Reporting Platform

**Key Findings**:
- **No Public API**: SIX Swiss Exchange does not provide programmatic REST API access
- **Web Portal Only**: Financial statements available through SER-AG website
- **XBRL Format**: Swiss companies file in XBRL (Swiss GAAP FER or IFRS taxonomy)
- **Access Method**: Manual download from company disclosure pages
- **e-Reporting Platform**: https://www.ser-ag.com/en/resources/notifications-market-participants/e-reporting.html

**Implementation**: `ch_six_fetcher.py`
- Inherits from `BaseXBRLFetcher`
- **Current Mode**: Manual file upload with structured directory guidance
- Parses Swiss XBRL using IFRS/Swiss GAAP FER taxonomy mapper
- Maps to CF Financial Period with quality score 95
- Auto-routes for stock_exchange = EBS
- Requires Swiss ISIN (CH + 10 digits, e.g., CH0038863350)

**Directory Structure** (manual upload):
```
sites/private/files/six/<ISIN>/Annual/<YYYY-MM-DD>/
  report.xhtml (or .xml)
```

**Example**:
```
sites/private/files/six/CH0038863350/Annual/2023-12-31/
  report.xhtml  # Nestlé 2023 annual report
```

**Search Instructions**:
1. Visit SIX company disclosure pages or SER-AG e-reporting platform
2. Search by company name or ISIN
3. Download annual report XBRL files
4. Place in correct directory structure
5. Run CF Security auto-import

**Currency**: CHF (Swiss Franc)

**Current Portfolio Securities**:
- NESN.SW (Nestlé, ISIN: CH0038863350)
- ROG.SW (Roche, ISIN: CH0012032048)

**Future Enhancement**: Optional Playwright automation if clear download patterns are identified (authentication may be required)

**Auto-routing**: Activates for stock_exchange = EBS when ISIN is set

---

### 🇨🇦 Canada (SEDAR+)

**Status**: Feasible  
**Priority**: MEDIUM (good API availability)

**Data Source**: SEDAR+ (System for Electronic Document Analysis and Retrieval)

**Key Findings**:
- **Public API**: SEDAR+ provides REST API (launched 2023, replacing old SEDAR)
- **XBRL Support**: Companies file in XBRL (IFRS or CA-GAAP)
- **Document Types**: Annual Information Forms (AIF), Financial Statements, Management Discussion
- **Rate Limits**: Moderate rate limits (exact limits undocumented)

**API Endpoints**:
```
Base URL: https://www.sedarplus.ca/csa-cpub/en/
Search: /search?q={issuer_name}
Filings: /filings/{issuer_id}
Documents: /document/{document_id}
```

**Implementation Steps**:
1. Map ticker to SEDAR issuer ID
2. Fetch filing list for issuer
3. Filter for financial statement filings
4. Download XBRL documents
5. Parse with IFRS taxonomy mapper

**Estimated Complexity**: MEDIUM (new API, documentation improving)

---

### 🇯🇵 Japan (EDINET)

**Status**: Feasible (with Japanese language support)  
**Priority**: MEDIUM (major market, language barrier)

**Data Source**: EDINET (FSA - Financial Services Agency)

**Key Findings**:
- **Public API**: EDINET API available (https://disclosure.edinet-fsa.go.jp/)
- **XBRL Format**: Financial statements in XBRL (JGAAP taxonomy)
- **English Support**: Limited - most filings in Japanese
- **Document Code System**: Uses EDINETCode for company identification
- **Rate Limits**: Not clearly documented

**API Endpoints**:
```
Base URL: https://disclosure.edinet-fsa.go.jp/api/v1/
Document List: /documents.json?date={YYYY-MM-DD}&type=2
Document: /documents/{docID}
```

**Implementation Challenges**:
- Japanese language processing required for many fields
- EDINETCode mapping to ticker symbols
- JGAAP taxonomy differences from IFRS/US-GAAP
- Date format and fiscal year conventions differ

**Recommended Approach**:
1. Focus on large-cap companies with English translations
2. Use EDINET API for structured XBRL data (avoids language issues for numbers)
3. Implement EDINETCode lookup/mapping table
4. Consider partnering with Japanese data provider for comprehensive coverage

**Estimated Complexity**: HIGH (language barrier, unique taxonomy)

---

### 🇦🇺 Australia (ASIC)

**Status**: Limited Access  
**Priority**: MEDIUM

**Data Source**: ASIC (Australian Securities and Investments Commission)

**Key Findings**:
- **No Public API**: ASIC does not provide a public API for financial filings
- **XBRL Format**: Companies file in XBRL (AIFRS - Australian IFRS)
- **Access Methods**: 
  - ASIC Connect (paid subscription)
  - ASX (Australian Securities Exchange) announcements platform
- **Alternative**: ASX provides some access to price-sensitive announcements

**Implementation Challenges**:
- Requires paid ASIC Connect account for official filings
- ASX announcements are primarily PDFs, not XBRL
- No free programmatic access

**Recommended Approach**:
1. Use ASX announcements API (free) for preliminary data
2. Fall back to Yahoo Finance for Australian stocks
3. Consider ASIC Connect subscription for production use if high-quality AU data needed

**Estimated Complexity**: HIGH (paywall, limited free access)

---

## Implementation Priority

### Phase 3A (Immediate) - Highest ROI based on current data
1. **UK Companies House (LSE/IOB)** ✅ IMPLEMENTED - Free API, excellent docs
2. **EU ESEF (GER/PAR/AMS/MIL/MCE)** ✅ IMPLEMENTED - Manual upload mode
3. **Hong Kong HKEX (HKG)** ✅ IMPLEMENTED - Manual upload mode
4. **Switzerland SIX (EBS)** ✅ IMPLEMENTED - Manual upload mode

### Phase 3B - Future Expansion
5. **Canada SEDAR+** ✅ Free API; not in DB yet but strategic
6. **Japan EDINET** ⚠️ Language + taxonomy differences
7. **Australia ASIC** ⚠️ Paid access required

### Phase 3C - Deferred / Low Priority
8. **US OTC (PNK/OQX)** ⚠️ Many issuers lack SEC filings; Yahoo fallback acceptable

---

## Technical Requirements

### Dependencies

```bash
# Phase 3A - UK/Canada
pip install requests beautifulsoup4 lxml

# Phase 3B - Hong Kong (web scraping)
pip install selenium playwright

# Phase 3B - Japan (language support)
pip install langdetect

# Already installed from Phase 2
python-xbrl>=2.1.0
```

### New DocType Fields

**CF Security** additions needed:
- `companies_house_number` (UK)
- `sedar_issuer_id` (Canada)
- `hkex_stock_code` (Hong Kong)
- `edinet_code` (Japan)
- `asx_code` (Australia)

### Configuration

**CF Settings** additions:
- API keys for each exchange
- Rate limit configuration
- Enable/disable specific regional fetchers

---

## Testing Strategy

1. **Unit Tests**: Taxonomy mapper, concept matching
2. **Integration Tests**: Each regional fetcher with sample XBRL files
3. **Live Tests**: Small set of well-known companies per exchange
4. **Fallback Tests**: Verify Yahoo Finance fallback when exchange fails

---

## Documentation Updates Needed

1. **DEPLOYMENT.md**: Add Phase 3 library requirements
2. **README.md**: Update supported exchanges table
3. **User Guide**: Add exchange-specific setup instructions
4. **API Docs**: Document new fetcher classes and taxonomy mapper

---

## Risk Assessment

| Exchange | API Access | Documentation | Complexity | Risk Level |
|----------|------------|---------------|------------|------------|
| UK Companies House | ✅ Free | ✅ Excellent | LOW | **LOW** |
| Canada SEDAR+ | ✅ Free | ⚠️ Improving | MEDIUM | **MEDIUM** |
| Hong Kong HKEX | ❌ No API | ❌ Poor | HIGH | **HIGH** |
| Japan EDINET | ✅ Free | ⚠️ Japanese | HIGH | **HIGH** |
| EU (Various) | ⚠️ Fragmented | ⚠️ Varies | HIGH | **HIGH** |
| Australia ASIC | ❌ Paid | ⚠️ Limited | HIGH | **HIGH** |

---

## Success Criteria

Phase 3 is considered successful when:

1. ✅ Taxonomy mapper supports all major accounting standards
2. ✅ BaseXBRLFetcher provides reusable foundation
3. ✅ At least 2 regional fetchers implemented and tested (UK + Canada)
4. ✅ Exchange detection automatically routes to correct fetcher
5. ✅ Quality score 95 maintained for regulatory filings
6. ✅ Fallback to Yahoo Finance works seamlessly when regional fetcher fails
7. ✅ Documentation complete for implemented exchanges

---

## Next Steps

1. ✅ **Completed**: Taxonomy mapper and base fetcher framework
2. **In Progress**: Refactor SEC Edgar fetcher to use base class
3. **Next**: Implement UK Companies House fetcher (highest priority)
4. **Then**: Implement Canada SEDAR+ fetcher
5. **Future**: Evaluate Hong Kong web scraping feasibility

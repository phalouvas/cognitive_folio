# Switzerland SIX Swiss Exchange Testing Guide

## Overview

This guide provides step-by-step instructions for testing the Switzerland SIX Swiss Exchange XBRL fetcher implementation. The fetcher supports manual upload of Swiss XBRL financial statements for securities listed on the SIX Swiss Exchange (stock_exchange = 'EBS').

## Prerequisites

### 1. CF Security Setup

Ensure Swiss securities have proper configuration:

```python
# In ERPNext, check CF Security document
- name: NESN.SW
- symbol: NESN.SW
- stock_exchange: EBS
- isin: CH0038863350  # REQUIRED for SIX fetcher
- currency: CHF
```

**CRITICAL**: Swiss ISIN must be present (format: CH + 10 digits)

### 2. Directory Structure

Create the manual upload directory structure:

```bash
cd /path/to/frappe-bench/sites/kainotomo.localhost/private/files
mkdir -p six/CH0038863350/Annual/2023-12-31
mkdir -p six/CH0012032048/Annual/2023-12-31
```

### 3. Sample Swiss XBRL Files

You'll need Swiss XBRL annual report files. Swiss companies typically file in:
- **IFRS format**: Most large Swiss multinationals (Nestlé, Roche, Novartis, etc.)
- **Swiss GAAP FER**: Some smaller domestic companies

**Where to find files**:
1. Company investor relations pages (often have "Financial Reports" section)
2. SIX Exchange Regulation website: https://www.ser-ag.com/en/
3. Company annual report downloads (look for XHTML/XML format)

**Expected file names**: `report.xhtml` or `report.xml`

## Test Cases

### Test 1: Basic Swiss XBRL Import (Nestlé)

1. **Download Nestlé XBRL report**:
   - Visit: https://www.nestle.com/investors/annual-report
   - Download 2023 annual report in XBRL format
   - Or use sample IFRS XBRL file

2. **Place file in directory**:
   ```bash
   cp nestle_2023.xhtml sites/private/files/six/CH0038863350/Annual/2023-12-31/report.xhtml
   ```

3. **Run import**:
   ```python
   # In ERPNext Console (bench --site <site> console)
   from cognitive_folio.cognitive_folio.doctype.cf_security.ch_six_fetcher import fetch_six_financials
   
   result = fetch_six_financials("NESN.SW")
   print(result)
   ```

4. **Expected Output**:
   ```python
   {
       'success': True,
       'total_periods': 1,
       'imported_count': 1,
       'data_source_used': 'SIX Swiss Exchange',
       'message': 'Successfully imported 1 financial period(s)'
   }
   ```

5. **Verify CF Financial Period**:
   - Check CF Financial Period list for NESN.SW
   - Verify data_source = "SIX Swiss Exchange"
   - Verify data_quality_score = 95
   - Check financial metrics populated correctly

### Test 2: Multiple Periods (Roche)

1. **Setup multiple years**:
   ```bash
   mkdir -p sites/private/files/six/CH0012032048/Annual/2022-12-31
   mkdir -p sites/private/files/six/CH0012032048/Annual/2023-12-31
   
   # Place XBRL files for both years
   cp roche_2022.xhtml sites/private/files/six/CH0012032048/Annual/2022-12-31/report.xhtml
   cp roche_2023.xhtml sites/private/files/six/CH0012032048/Annual/2023-12-31/report.xhtml
   ```

2. **Run import**:
   ```python
   from cognitive_folio.cognitive_folio.doctype.cf_security.ch_six_fetcher import fetch_six_financials
   
   result = fetch_six_financials("ROG.SW")
   print(result)
   ```

3. **Expected**: Both 2022 and 2023 periods imported

### Test 3: Auto-Import via CF Security

1. **Open CF Security form** for NESN.SW

2. **Click "Auto Import Financial Periods"** button

3. **System should**:
   - Detect stock_exchange = EBS
   - Route to `ch_six_fetcher.fetch_six_financials()`
   - Parse XBRL files from `sites/private/files/six/CH0038863350/Annual/`
   - Create CF Financial Period records

4. **Verify message**: "Successfully imported X financial period(s) from SIX Swiss Exchange (quality: 95)"

### Test 4: Missing ISIN Error Handling

1. **Create test security without ISIN**:
   ```python
   # In ERPNext Console
   doc = frappe.get_doc("CF Security", "TEST.SW")
   doc.stock_exchange = "EBS"
   doc.isin = ""  # Blank ISIN
   doc.save()
   ```

2. **Try import**:
   ```python
   from cognitive_folio.cognitive_folio.doctype.cf_security.ch_six_fetcher import fetch_six_financials
   result = fetch_six_financials("TEST.SW")
   ```

3. **Expected**: Error message requiring ISIN

### Test 5: No Files Available (Fallback to Yahoo)

1. **Setup security with EBS exchange but no uploaded files**:
   ```python
   # Ensure no files in sites/private/files/six/CH0038863350/Annual/
   rm -rf sites/private/files/six/CH0038863350/Annual/*
   ```

2. **Run auto-import** from CF Security form

3. **Expected behavior**:
   - SIX fetcher finds no files
   - Logs message about missing uploads
   - Falls back to Yahoo Finance
   - Imports with quality score 85

### Test 6: Swiss GAAP FER vs IFRS Detection

Swiss companies may use different accounting standards:

1. **Test with IFRS file** (Nestlé, Roche):
   - Should map concepts using IFRS taxonomy
   - Common tags: `ifrs:Revenue`, `ifrs:Assets`, etc.

2. **Test with Swiss GAAP FER file** (if available):
   - Should detect Swiss GAAP taxonomy
   - Taxonomy mapper handles both standards

3. **Verify taxonomy detection** in logs

## Common Swiss ISINs for Testing

| Company | Symbol | ISIN | Accounting Standard |
|---------|--------|------|---------------------|
| Nestlé | NESN.SW | CH0038863350 | IFRS |
| Roche | ROG.SW | CH0012032048 | IFRS |
| Novartis | NOVN.SW | CH0012005267 | IFRS |
| UBS | UBSG.SW | CH0244767585 | IFRS |
| Zurich Insurance | ZURN.SW | CH0011075394 | IFRS |
| ABB | ABBN.SW | CH0012221716 | IFRS |

## Troubleshooting

### Issue: "ISIN is required"

**Solution**: Add Swiss ISIN (CH + 10 digits) to CF Security:
```python
doc = frappe.get_doc("CF Security", "NESN.SW")
doc.isin = "CH0038863350"
doc.save()
```

### Issue: "No manual uploads found"

**Solution**: 
1. Check directory path: `sites/private/files/six/<ISIN>/Annual/<YYYY-MM-DD>/`
2. Ensure file is named `report.xhtml` or `report.xml`
3. Verify ISIN in path matches CF Security ISIN

### Issue: "Invalid Swiss ISIN Format"

**Solution**: Swiss ISINs must be 12 characters: `CH` + 10 digits
- ✅ Valid: `CH0038863350`
- ❌ Invalid: `CH038863350` (only 9 digits)
- ❌ Invalid: `NESN.SW` (not an ISIN)

### Issue: XBRL parsing errors

**Check**:
1. File is valid XBRL/iXBRL format (not PDF or HTML)
2. File contains required XBRL namespaces
3. Review error logs: `bench --site <site> logs`

### Issue: Wrong financial data extracted

**Debug steps**:
1. Check taxonomy detected in logs (should be IFRS or Swiss GAAP FER)
2. Verify taxonomy mapper has correct concept mappings
3. Inspect XBRL file structure manually
4. Check if company uses custom extensions

## Validation Checklist

After running tests, verify:

- [ ] CF Financial Period records created
- [ ] `data_source` = "SIX Swiss Exchange"
- [ ] `data_quality_score` = 95
- [ ] Financial metrics populated:
  - [ ] Revenue
  - [ ] Net Income
  - [ ] Total Assets
  - [ ] Total Equity
  - [ ] Operating Cash Flow
- [ ] Period dates match file directory dates
- [ ] Currency = CHF
- [ ] No duplicate periods created
- [ ] Fallback to Yahoo Finance works when files missing

## Performance Notes

- **Manual upload**: No API rate limits
- **File parsing**: XBRL parsing is CPU-intensive (1-3 seconds per file)
- **Batch import**: Process multiple securities sequentially to avoid memory issues

## Future Enhancements

1. **Playwright automation**: Auto-download from SIX company pages (authentication required)
2. **Direct API**: If SIX provides official API access in future
3. **Swiss GAAP FER taxonomy**: Enhanced mapping for non-IFRS Swiss companies

## Support

For issues or questions:
1. Check error logs: `bench --site <site> logs`
2. Review XBRL file structure
3. Verify ISIN format and directory paths
4. Consult `PHASE3_IMPLEMENTATION.md` for detailed architecture

---

**Test Status**: Ready for manual XBRL upload testing with Swiss securities (NESN.SW, ROG.SW)

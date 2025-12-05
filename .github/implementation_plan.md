# Cognitive Folio Financial Data Pipeline Refactoring Plan

## Executive Summary

This document outlines the implementation plan for refactoring the cognitive_folio financial data pipeline. The goal is to simplify the architecture by removing the CF Financial Period DocType, eliminating all code references to it, and leveraging edgartools' built-in caching and multi-period analysis capabilities.

**Current Architecture:**
```
CF Security → fetch_data() → CF Financial Period records → format_periods_for_ai() → markdown → variable replacement → AI prompts
```

**Target Architecture:**
```
CF Security → fetch_data() → yfinance JSON storage → edgartools live fetch with caching → XBRLS.from_filings() → .to_markdown() → variable injection → AI prompts
```

## Design Rationale

1. **Remove Database Complexity**: CF Financial Period normalization is complex and varies significantly across company XBRL structures
2. **Leverage Built-in Caching**: edgartools provides automatic caching of Company data, filing downloads, and XBRL parsing
3. **Multi-Period Analysis**: XBRLS.from_filings() handles period stitching intelligently
4. **AI-Ready Output**: .to_markdown() provides clean tables that AI can analyze and calculate derived metrics from
5. **Simplification**: Raw financial statements are sufficient - AI can calculate ratios, margins, growth rates on-demand

## Variable System Design

### New Variable Syntax

**Edgar Variables (US Companies with SEC Filings):**
```
{{edgar:income:annual:5:markdown}}          → 5-year annual income statement
{{edgar:income:quarterly:8:markdown}}       → 8-quarter income statement
{{edgar:balance:annual:3:markdown}}         → 3-year annual balance sheet
{{edgar:cashflow:quarterly:4:markdown}}     → 4-quarter cash flow statement
{{edgar:equity:annual:5:markdown}}          → 5-year statement of changes in equity
```

**YFinance Variables (Non-US Companies or Fallback):**
```
{{yfinance:profit_loss:annual:markdown}}    → Annual P&L from yfinance JSON
{{yfinance:balance_sheet:quarterly:markdown}} → Quarterly balance sheet from yfinance JSON
{{yfinance:cash_flow:annual:markdown}}      → Annual cash flow from yfinance JSON
```

**Ticker Info Variables (Market Data):**
```
{{ticker_info.marketCap}}                   → Market capitalization
{{ticker_info.forwardPE}}                   → Forward P/E ratio
{{ticker_info.beta}}                        → Beta coefficient
{{ticker_info.sector}}                      → Company sector
{{ticker_info.industry}}                    → Company industry
```

### Variable Resolution Logic

1. **Parse Variable**: Extract type (edgar/yfinance), statement, period type, count, format
2. **Check Company Type**: US companies with CIK use edgar, others use yfinance
3. **Edgar Path**:
   - Use edgartools Company.get_filings() to fetch 10-K/10-Q
   - Create XBRLS.from_filings(filings)
   - Call appropriate statement method (.income_statement(), .balance_sheet(), etc.)
   - Convert to markdown with .to_markdown()
4. **YFinance Path**:
   - Read stored JSON from CF Security fields (profit_loss, balance_sheet, cash_flow)
   - Parse JSON and convert to markdown table
   - Filter by period type (annual/quarterly)
5. **Return Result**: Inject markdown into prompt

## Implementation Steps

### Phase 1: Preparation and Analysis

#### Step 1.1: Audit CF Financial Period Dependencies
**Task**: Search entire codebase for CF Financial Period references
**Commands**:
```bash
cd /workspace/development/frappe-bench/apps/cognitive_folio
grep -r "CF Financial Period" --include="*.py" --include="*.json"
grep -r "cf_financial_period" --include="*.py" --include="*.json"
grep -r "from_cf_financial_period" --include="*.py"
```

**Expected Findings**:
- sec_edgar_fetcher.py: _upsert_period() function
- cf_security.py: _create_financial_periods_from_yahoo() function
- helper.py: format_periods_for_ai() function
- Any DocType JSON definitions

**Deliverable**: List of all files referencing CF Financial Period to be removed or refactored

#### Step 1.2: Backup Current Prompt Templates
**Task**: Save copies of current prompt templates before modification
**Files to Backup**:
- cognitive_folio/cognitive_folio/doctype/cf_security/prompt_1.md
- cognitive_folio/cognitive_folio/doctype/cf_security/prompt_2.md
- cognitive_folio/cognitive_folio/doctype/cf_security/prompt_3.md

**Command**:
```bash
cd /workspace/development/frappe-bench/apps/cognitive_folio/cognitive_folio/doctype/cf_security
cp prompt_1.md prompt_1.md.backup
cp prompt_2.md prompt_2.md.backup
cp prompt_3.md prompt_3.md.backup
```

### Phase 2: Remove CF Financial Period

#### Step 2.1: Remove CF Financial Period DocType
**Task**: Delete DocType definition and generated files

**Files to Remove**:
- cognitive_folio/cognitive_folio/doctype/cf_financial_period/
  - cf_financial_period.json
  - cf_financial_period.py
  - __init__.py
  - Any test files

**Command**:
```bash
cd /workspace/development/frappe-bench/apps/cognitive_folio
rm -rf cognitive_folio/doctype/cf_financial_period/
```

**Post-Action**: Run bench migrate to clean up database tables (manual step for user)

#### Step 2.2: Remove CF Financial Period Creation Logic

**File**: `cognitive_folio/cognitive_folio/utils/sec_edgar_fetcher.py`

**Changes Required**:
1. Remove `_upsert_period()` function (lines ~800-900)
2. Remove all calls to `_upsert_period()` in `_extract_financial_data()`
3. Remove CF Financial Period import statement
4. Keep XBRL extraction logic for potential future use

**Specific Code Removals**:
```python
# Remove this import
from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import (
    create_or_update_financial_period
)

# Remove _upsert_period() function entirely

# Remove these calls in _extract_financial_data():
_upsert_period(security_name, period_end, period_start, "annual", ...)
_upsert_period(security_name, period_end, period_start, "quarterly", ...)
```

**File**: `cognitive_folio/cognitive_folio/doctype/cf_security/cf_security.py`

**Changes Required**:
1. Remove `_create_financial_periods_from_yahoo()` method
2. Remove any CF Financial Period queries
3. Keep yfinance JSON storage in profit_loss, balance_sheet, cash_flow fields

#### Step 2.3: Remove format_periods_for_ai() Function

**File**: `cognitive_folio/cognitive_folio/utils/helper.py`

**Changes Required**:
1. Remove `format_periods_for_ai()` function
2. Remove any CF Financial Period imports
3. Keep other utility functions intact

#### Step 2.4: Verify Removal of CF Financial Period References
**Task**: Confirm no references remain in the repository after code changes

**Command**:
```bash
cd /workspace/development/frappe-bench/apps/cognitive_folio
rg "CF Financial Period" -i
rg "cf_financial_period" -i
rg "from_cf_financial_period" -i
```

**Expected Result**: No matches returned

### Phase 3: Implement New Variable Handler

#### Step 3.1: Create Edgar Variable Handler

**File**: `cognitive_folio/cognitive_folio/utils/helper.py`

**New Function**:
```python
def handle_edgar_variable(security_name: str, statement_type: str, 
                          period_type: str, count: int, output_format: str) -> str:
    """
    Handle {{edgar:statement:period:count:format}} variables.
    
    Args:
        security_name: Name of CF Security document
        statement_type: income, balance, cashflow, equity
        period_type: annual, quarterly
        count: Number of periods to retrieve
        output_format: markdown (only format supported currently)
    
    Returns:
        Markdown formatted financial statement
    
    Example:
        {{edgar:income:annual:5:markdown}} → 5-year income statement
    """
    import frappe
    from edgar import Company
    from edgar.xbrl import XBRLS
    
    # Get security document
    security = frappe.get_doc("CF Security", security_name)
    
    # Check if company has CIK
    if not security.cik:
        return f"<!-- No CIK available for {security_name} -->"
    
    # Get company
    company = Company(security.cik)
    
    # Determine filing form based on period type
    filing_form = "10-K" if period_type == "annual" else "10-Q"
    
    # Fetch filings
    filings = company.get_filings(form=filing_form).latest(count)
    
    if not filings:
        return f"<!-- No {filing_form} filings found for {security_name} -->"
    
    # Create XBRLS multi-period view
    xbrls = XBRLS.from_filings(filings)
    
    # Get appropriate statement
    statement_map = {
        "income": xbrls.income_statement,
        "balance": xbrls.balance_sheet,
        "cashflow": xbrls.cashflow_statement,
        "equity": xbrls.statement_of_equity
    }
    
    statement_method = statement_map.get(statement_type)
    if not statement_method:
        return f"<!-- Invalid statement type: {statement_type} -->"
    
    # Get statement
    statement = statement_method()
    
    # Convert to markdown
    if output_format == "markdown":
        return statement.to_markdown()
    
    return f"<!-- Unsupported format: {output_format} -->"
```

#### Step 3.2: Create YFinance Variable Handler

**File**: `cognitive_folio/cognitive_folio/utils/helper.py`

**New Function**:
```python
def handle_yfinance_variable(security_name: str, statement_type: str, 
                             period_type: str, output_format: str) -> str:
    """
    Handle {{yfinance:statement:period:format}} variables.
    
    Args:
        security_name: Name of CF Security document
        statement_type: profit_loss, balance_sheet, cash_flow
        period_type: annual, quarterly
        output_format: markdown (only format supported currently)
    
    Returns:
        Markdown formatted financial statement from stored yfinance JSON
    
    Example:
        {{yfinance:profit_loss:annual:markdown}} → Annual P&L from yfinance
    """
    import frappe
    import json
    import pandas as pd
    
    # Get security document
    security = frappe.get_doc("CF Security", security_name)
    
    # Get stored JSON field
    field_map = {
        "profit_loss": "profit_loss",
        "balance_sheet": "balance_sheet", 
        "cash_flow": "cash_flow"
    }
    
    field_name = field_map.get(statement_type)
    if not field_name:
        return f"<!-- Invalid statement type: {statement_type} -->"
    
    # Get JSON data
    json_data = getattr(security, field_name, None)
    if not json_data:
        return f"<!-- No {statement_type} data available for {security_name} -->"
    
    try:
        # Parse JSON
        data = json.loads(json_data)
        
        # Filter by period type if structure includes it
        if period_type in data:
            data = data[period_type]
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Convert to markdown
        if output_format == "markdown":
            return df.to_markdown(index=True)
        
        return f"<!-- Unsupported format: {output_format} -->"
        
    except Exception as e:
        return f"<!-- Error parsing {statement_type}: {str(e)} -->"
```

#### Step 3.3: Update replace_variables() Function

**File**: `cognitive_folio/cognitive_folio/utils/helper.py`

**Changes Required**:
1. Add pattern matching for {{edgar:*}} variables
2. Add pattern matching for {{yfinance:*}} variables
3. Remove {{periods:*}} pattern matching
4. Keep {{ticker_info.*}} pattern matching

**New Code**:
```python
def replace_variables(text: str, security_name: str) -> str:
    """
    Replace template variables in text with actual values.
    
    Supported patterns:
    - {{edgar:statement:period:count:format}}
    - {{yfinance:statement:period:format}}
    - {{ticker_info.field}}
    
    Args:
        text: Template text with variables
        security_name: Name of CF Security document
    
    Returns:
        Text with variables replaced
    """
    import re
    import frappe
    import json
    
    # Pattern for edgar variables: {{edgar:income:annual:5:markdown}}
    edgar_pattern = r'\{\{edgar:(\w+):(\w+):(\d+):(\w+)\}\}'
    
    def edgar_replacer(match):
        statement, period, count, fmt = match.groups()
        return handle_edgar_variable(security_name, statement, period, int(count), fmt)
    
    text = re.sub(edgar_pattern, edgar_replacer, text)
    
    # Pattern for yfinance variables: {{yfinance:profit_loss:annual:markdown}}
    yfinance_pattern = r'\{\{yfinance:(\w+):(\w+):(\w+)\}\}'
    
    def yfinance_replacer(match):
        statement, period, fmt = match.groups()
        return handle_yfinance_variable(security_name, statement, period, fmt)
    
    text = re.sub(yfinance_pattern, yfinance_replacer, text)
    
    # Pattern for ticker_info: {{ticker_info.marketCap}}
    ticker_pattern = r'\{\{ticker_info\.(\w+)\}\}'
    
    def ticker_replacer(match):
        field = match.group(1)
        security = frappe.get_doc("CF Security", security_name)
        
        if not security.ticker_info:
            return f"<!-- No ticker info available -->"
        
        try:
            ticker_data = json.loads(security.ticker_info)
            value = ticker_data.get(field, f"<!-- Field {field} not found -->")
            return str(value)
        except:
            return f"<!-- Error parsing ticker info -->"
    
    text = re.sub(ticker_pattern, ticker_replacer, text)
    
    return text
```

### Phase 4: Update Prompt Templates

#### Step 4.1: Update prompt_1.md (Baseline Evaluation)

**File**: `cognitive_folio/cognitive_folio/doctype/cf_security/prompt_1.md`

**Current Variables to Replace**:
```
{{periods:annual:10:markdown}} → {{edgar:income:annual:5:markdown}}
                                  {{edgar:balance:annual:5:markdown}}
                                  {{edgar:cashflow:annual:5:markdown}}
```

**Rationale**: Split single variable into three separate statements for clarity. AI can analyze all three together.

**Additional Context to Add**:
```markdown
## Financial Statements (5-Year Historical Data)

### Income Statement
{{edgar:income:annual:5:markdown}}

### Balance Sheet
{{edgar:balance:annual:5:markdown}}

### Cash Flow Statement
{{edgar:cashflow:annual:5:markdown}}

**Note**: If Edgar data is unavailable (non-US company), fallback data:
{{yfinance:profit_loss:annual:markdown}}
{{yfinance:balance_sheet:annual:markdown}}
{{yfinance:cash_flow:annual:markdown}}
```

#### Step 4.2: Update prompt_2.md (Quarterly Updates)

**File**: `cognitive_folio/cognitive_folio/doctype/cf_security/prompt_2.md`

**Current Variables to Replace**:
```
{{periods:quarterly:4:markdown}} → {{edgar:income:quarterly:4:markdown}}
                                    {{edgar:balance:quarterly:4:markdown}}
                                    {{edgar:cashflow:quarterly:4:markdown}}
```

**Additional Context**:
```markdown
## Recent Quarterly Performance (Last 4 Quarters)

### Income Statement
{{edgar:income:quarterly:4:markdown}}

### Balance Sheet
{{edgar:balance:quarterly:4:markdown}}

### Cash Flow Statement
{{edgar:cashflow:quarterly:4:markdown}}
```

#### Step 4.3: Update prompt_3.md (JSON Auto-Update)

**File**: `cognitive_folio/cognitive_folio/doctype/cf_security/prompt_3.md`

**Changes**: Similar to prompt_2.md with focus on JSON output format

### Phase 5: Testing and Validation

#### Step 5.1: Unit Tests for Variable Handlers

**File**: `cognitive_folio/cognitive_folio/tests/test_variable_handlers.py` (new file)

**Test Cases**:
```python
import unittest
from cognitive_folio.utils.helper import handle_edgar_variable, handle_yfinance_variable

class TestVariableHandlers(unittest.TestCase):
    
    def test_edgar_income_statement(self):
        """Test edgar income statement variable"""
        result = handle_edgar_variable("AAPL", "income", "annual", 5, "markdown")
        self.assertIn("Revenue", result)
        self.assertIn("Net Income", result)
    
    def test_edgar_balance_sheet(self):
        """Test edgar balance sheet variable"""
        result = handle_edgar_variable("AAPL", "balance", "annual", 3, "markdown")
        self.assertIn("Assets", result)
        self.assertIn("Liabilities", result)
    
    def test_yfinance_fallback(self):
        """Test yfinance fallback for non-US companies"""
        result = handle_yfinance_variable("TEST_SECURITY", "profit_loss", "annual", "markdown")
        # Should return comment if no data
        self.assertIn("<!--", result)
    
    def test_invalid_statement_type(self):
        """Test handling of invalid statement type"""
        result = handle_edgar_variable("AAPL", "invalid", "annual", 5, "markdown")
        self.assertIn("Invalid statement type", result)
```

#### Step 5.2: Integration Test with Real Security

**Manual Test Steps**:
1. Create test CF Security: "TEST - Apple Inc" with CIK "0000320193"
2. Run fetch_data() to populate yfinance JSON
3. Test edgar variables:
   - Open CF Chat Message
   - Create message with prompt containing {{edgar:income:annual:5:markdown}}
   - Run prepare_prompt() and verify markdown output
4. Test yfinance variables:
   - Create CF Security for non-US company (no CIK)
   - Test {{yfinance:profit_loss:annual:markdown}}
   - Verify fallback works

#### Step 5.3: Performance Testing

**Metrics to Monitor**:
1. **First Load Time**: Time to generate markdown on first call (no cache)
2. **Cached Load Time**: Time to generate markdown on subsequent calls
3. **Memory Usage**: RAM consumption during XBRLS processing
4. **Prompt Size**: Total character count of expanded prompts

**Expected Performance**:
- First load: ~5-10 seconds (SEC Edgar API call + XBRL parsing)
- Cached load: <1 second (edgartools caching)
- Memory: <500MB per security
- Prompt size: ~10-50KB per statement

### Phase 6: Migration and Cleanup

#### Step 6.1: Database Cleanup

**Manual Steps for User**:
```bash
cd /workspace/development/frappe-bench
bench --site kainotomo.localhost console
```

**Python Commands**:
```python
# Count existing CF Financial Period records
frappe.db.count("CF Financial Period")

# Optional: Export data before deletion (backup)
import json
periods = frappe.get_all("CF Financial Period", 
                         fields=["*"], 
                         limit=None)
with open("/tmp/cf_periods_backup.json", "w") as f:
    json.dump(periods, f, indent=2, default=str)

# Delete all CF Financial Period records
frappe.db.delete("CF Financial Period")
frappe.db.commit()

# Run migrate to clean up DocType
exit()
```

```bash
bench --site kainotomo.localhost migrate
bench --site kainotomo.localhost clear-cache
```

#### Step 6.2: Update Dependencies

**File**: `cognitive_folio/pyproject.toml`

**Verify Dependencies**:
```toml
[project]
dependencies = [
    "frappe",
    "edgartools>=4.34.1",  # Ensure minimum version
    "yfinance",
    "pandas",
]
```

**Command**:
```bash
cd /workspace/development/frappe-bench
./env/bin/pip install --upgrade edgartools
./env/bin/pip list | grep edgartools  # Verify version >= 4.34.1
```

#### Step 6.3: Documentation Updates

**Files to Update**:
1. `cognitive_folio/README.md`: Update architecture diagram and variable documentation
2. `cognitive_folio/documentation/VARIABLES.md`: Create new doc explaining variable syntax
3. `cognitive_folio/documentation/MIGRATION.md`: Document CF Financial Period removal

### Phase 7: Deployment

#### Step 7.1: Development Environment Validation

**Checklist**:
- [ ] All CF Financial Period references removed
- [ ] New variable handlers implemented and tested
- [ ] Prompt templates updated
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] No errors in console when generating prompts
- [ ] Edgar caching working (verify faster second loads)

#### Step 7.2: Staging Deployment

**Steps**:
1. Deploy to staging environment
2. Test with 5-10 real securities
3. Monitor logs for errors
4. Verify prompt generation performance
5. Test AI chat with new prompts

#### Step 7.3: Production Deployment

**Pre-Deployment**:
```bash
# Backup production database
cd /workspace/development/frappe-bench
bench --site kainotomo.localhost backup

# Note backup location
ls -lh sites/kainotomo.localhost/private/backups/
```

**Deployment**:
```bash
# Pull latest code
cd /workspace/development/frappe-bench/apps/cognitive_folio
git pull origin master

# Run migrations
cd /workspace/development/frappe-bench
bench --site kainotomo.localhost migrate

# Clear cache
bench --site kainotomo.localhost clear-cache

# Restart services
bench restart
```

**Post-Deployment Monitoring**:
- Monitor error logs: `tail -f sites/kainotomo.localhost/logs/web.error.log`
- Test 3-5 securities immediately
- Monitor performance metrics
- Watch for any cache-related issues

## Rollback Plan

### If Issues Occur

**Step 1: Restore Code**
```bash
cd /workspace/development/frappe-bench/apps/cognitive_folio
git revert <commit-hash>  # Revert to previous version
```

**Step 2: Restore Database**
```bash
cd /workspace/development/frappe-bench

# List backups
ls -lh sites/kainotomo.localhost/private/backups/

# Restore
bench --site kainotomo.localhost restore <backup-file>
```

**Step 3: Restart**
```bash
bench --site kainotomo.localhost migrate
bench --site kainotomo.localhost clear-cache
bench restart
```

## Success Criteria

### Functional Requirements
✅ All CF Financial Period references removed from codebase
✅ Edgar variables work for US companies with CIK
✅ YFinance variables work as fallback
✅ Prompt generation completes in <2 seconds (cached)
✅ AI chat messages contain properly formatted markdown tables
✅ No database bloat from financial periods

### Performance Requirements
✅ First edgar call: <10 seconds
✅ Cached edgar call: <1 second
✅ Memory usage: <500MB per security
✅ No timeout errors during prompt generation

### Quality Requirements
✅ All unit tests passing
✅ No errors in error logs
✅ Code coverage >80% for new functions
✅ Documentation updated and accurate

## Timeline Estimate

- **Phase 1 (Preparation)**: 1 hour
- **Phase 2 (Remove CF Period)**: 2 hours
- **Phase 3 (New Handlers)**: 4 hours
- **Phase 4 (Update Prompts)**: 2 hours
- **Phase 5 (Testing)**: 4 hours
- **Phase 6 (Migration)**: 2 hours
- **Phase 7 (Deployment)**: 2 hours

**Total Estimated Time**: 17 hours

## Risk Assessment

### High Risk Items
1. **Edgar API Rate Limits**: SEC Edgar may rate limit during testing
   - Mitigation: Use caching extensively, test with small dataset first

2. **Variable Parsing Errors**: Regex patterns may miss edge cases
   - Mitigation: Comprehensive unit tests, add error handling

3. **Missing CIK Data**: Some US companies may not have CIK mapped
   - Mitigation: YFinance fallback, add CIK lookup utility

### Medium Risk Items
1. **XBRLS Parsing Failures**: Some filings may have non-standard XBRL
   - Mitigation: Add try-catch blocks, return error comments

2. **Performance Degradation**: First loads may feel slow to users
   - Mitigation: Add loading indicators, consider pre-caching popular securities

### Low Risk Items
1. **Markdown Formatting Issues**: Tables may not render perfectly
   - Mitigation: Test with multiple securities, adjust formatting

## Appendix

### Useful Commands

**Search for CF Financial Period references**:
```bash
cd /workspace/development/frappe-bench/apps/cognitive_folio
rg "CF Financial Period" -i
rg "cf_financial_period" -i
```

**Test edgartools in console**:
```python
from edgar import Company
company = Company("AAPL")
filings = company.get_filings(form="10-K").latest(3)
from edgar.xbrl import XBRLS
xbrls = XBRLS.from_filings(filings)
print(xbrls.income_statement().to_markdown())
```

**Monitor bench logs**:
```bash
cd /workspace/development/frappe-bench
tail -f sites/kainotomo.localhost/logs/web.error.log
tail -f sites/kainotomo.localhost/logs/web.log
```

### Reference Links

- **edgartools Documentation**: https://edgartools.readthedocs.io/
- **XBRLS API**: https://edgartools.readthedocs.io/en/latest/getting-xbrl/
- **Frappe DocType Guide**: https://frappeframework.com/docs/user/en/basics/doctypes
- **SEC Edgar Search**: https://www.sec.gov/edgar/searchedgar/companysearch.html

---

**Document Version**: 1.0  
**Created**: December 5, 2025  
**Last Updated**: December 5, 2025  
**Status**: Ready for Implementation
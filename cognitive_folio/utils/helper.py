import json
import re
import os
from datetime import datetime

def _handle_wildcard_pattern(data, path_parts):
    """
    Handle wildcard patterns like *.content.title to extract values from all array items
    Returns a comma-separated string of all matching values
    """
    if not path_parts:
        return str(data) if data is not None else ""
    
    current_part = path_parts[0]
    remaining_parts = path_parts[1:]
    
    if current_part == 'ARRAY':
        # Wildcard - process all items in the current data
        if isinstance(data, list):
            results = []
            for item in data:
                if remaining_parts:
                    # Continue processing the remaining path
                    result = _navigate_nested_path(item, remaining_parts)
                    if result is not None and result != "":
                        results.append(str(result))
                else:
                    # No more path parts, add the item itself
                    if item is not None:
                        results.append(str(item))
            return ", ".join(results)
        elif isinstance(data, dict):
            # If it's a dict, process all values
            results = []
            for value in data.values():
                if remaining_parts:
                    result = _navigate_nested_path(value, remaining_parts)
                    if result is not None and result != "":
                        results.append(str(result))
                else:
                    if value is not None:
                        results.append(str(value))
            return ", ".join(results)
        else:
            return ""
    else:
        # Regular path part
        return _navigate_nested_path(data, path_parts)

def _navigate_nested_path(data, path_parts):
    """
    Navigate through a nested path without wildcards
    """
    current_data = data
    for part in path_parts:
        if isinstance(current_data, dict):
            current_data = current_data.get(part)
        elif isinstance(current_data, list):
            try:
                index = int(part)
                if 0 <= index < len(current_data):
                    current_data = current_data[index]
                else:
                    current_data = None
            except ValueError:
                current_data = None
                break
        else:
            current_data = None
            break
    
    return current_data

def replace_variables(match, doc):
    variable_name = match.group(1)
    try:
        
        # Handle nested JSON variables like {{field_name.key}} or {{field_name.0.key}} for arrays
        if '.' in variable_name:
            parts = variable_name.split('.')
            field_name = parts[0]
            nested_path = parts[1:]  # Remaining path parts
            
            field_value = getattr(doc, field_name, None)
            if field_value:
                try:
                    # Try to parse as JSON
                    json_data = json.loads(field_value)
                    
                    # Check if we have a wildcard pattern
                    if 'ARRAY' in nested_path:
                        return _handle_wildcard_pattern(json_data, nested_path)
                    
                    # Navigate through the nested path using the helper function
                    current_data = _navigate_nested_path(json_data, nested_path)
                    
                    if current_data is not None:
                        return str(current_data)
                    else:
                        return ""
                except json.JSONDecodeError:
                    # If not valid JSON, return empty string
                    return ""
            else:
                return ""
        else:
            # Handle regular doc field variables
            field_value = getattr(doc, variable_name, None)
            if field_value is not None:
                return str(field_value)
            else:
                return ""
    except (AttributeError, IndexError, ValueError):
        return match.group(0)

def clear_string(content_string: str) -> dict:
    """
    Convert a string to a JSON object.
    If the string is not valid JSON, return an empty dictionary.
    """
    # Parse the JSON from the content string, removing any Markdown formatting
    if content_string.startswith('```') and '```' in content_string[3:]:
        # Extract content between the first and last backtick markers
        content_string = content_string.split('```', 2)[1]
        # Remove the language identifier if present (e.g., 'json\n')
        if '\n' in content_string:
            content_string = content_string.split('\n', 1)[1]
        # Remove trailing backticks if any remain
        if '```' in content_string:
            content_string = content_string.split('```')[0]

    # Replace problematic control characters and normalize whitespace
    content_string = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content_string)
    
    # Fix JSON formatting issues - improved approach for handling newlines in strings
    # First, properly escape newlines that appear within JSON string values
    lines = content_string.split('\n')
    fixed_content = []
    current_line = ""
    in_string = False
    escape_next = False
    
    for line in lines:
        i = 0
        while i < len(line):
            char = line[i]
            
            if escape_next:
                current_line += char
                escape_next = False
            elif char == '\\':
                current_line += char
                escape_next = True
            elif char == '"' and not escape_next:
                current_line += char
                in_string = not in_string
            else:
                current_line += char
            
            i += 1
        
        # If we're at the end of a line and inside a string, escape the newline
        if in_string and line != lines[-1]:  # Not the last line
            current_line += '\\n'
        else:
            # We're not in a string or this is the last line
            fixed_content.append(current_line)
            current_line = ""
    
    # Add any remaining content
    if current_line:
        fixed_content.append(current_line)
    
    content_string = '\n'.join(fixed_content)
    
    # Additional cleanup for HTML entities and special characters
    content_string = content_string.replace('&nbsp;', ' ')
    content_string = content_string.replace('\t', '    ')
    
    return content_string


def _parse_json_field(field_value):
    """Safely parse JSON field values coming from Frappe documents."""
    if field_value is None:
        return None
    if isinstance(field_value, (dict, list)):
        return field_value
    if isinstance(field_value, str):
        try:
            return json.loads(field_value)
        except json.JSONDecodeError:
            return None
    return None


def _json_to_markdown_table(data):
    """Convert a JSON-like object to a markdown table; return empty string if impossible."""
    try:
        import pandas as pd

        if data is None:
            return ""

        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            # If dict values are dict/list, orient as index; else single-row
            if all(isinstance(v, (dict, list)) for v in data.values()):
                df = pd.DataFrame(data).transpose()
            else:
                df = pd.DataFrame([data])
        else:
            return ""

        if df.empty:
            return ""

        return df.to_markdown(index=True)
    except Exception:
        return ""


def get_cached_yfinance_data(security, annual_years=None, quarterly_count=None):
    """Return yfinance-stored statements from CF Security as structured objects.
    
    Args:
        security: CF Security document
        annual_years: Number of annual periods to return (None = all)
        quarterly_count: Number of quarterly periods to return (None = all)
    """
    def _slice_periods(data, count):
        """Slice JSON data to requested number of periods."""
        if data is None or count is None:
            return data
        if isinstance(data, dict):
            # Assumes dict keys are period labels (dates); take first N items
            return dict(list(data.items())[:count])
        elif isinstance(data, list):
            return data[:count]
        return data
    
    annual_income = _parse_json_field(getattr(security, "profit_loss", None))
    quarterly_income = _parse_json_field(getattr(security, "quarterly_profit_loss", None))
    annual_balance = _parse_json_field(getattr(security, "balance_sheet", None))
    quarterly_balance = _parse_json_field(getattr(security, "quarterly_balance_sheet", None))
    annual_cashflow = _parse_json_field(getattr(security, "cash_flow", None))
    quarterly_cashflow = _parse_json_field(getattr(security, "quarterly_cash_flow", None))
    
    return {
        "income_statement_annual": _slice_periods(annual_income, annual_years),
        "income_statement_quarterly": _slice_periods(quarterly_income, quarterly_count),
        "balance_sheet_annual": _slice_periods(annual_balance, annual_years),
        "balance_sheet_quarterly": _slice_periods(quarterly_balance, quarterly_count),
        "cashflow_statement_annual": _slice_periods(annual_cashflow, annual_years),
        "cashflow_statement_quarterly": _slice_periods(quarterly_cashflow, quarterly_count),
    }


def _render_yfinance_markdown(yf_data):
    """Render yfinance data to markdown; skip empty parts; return combined markdown."""
    sections = []
    mapping = [
        ("Income Statement (Annual)", yf_data.get("income_statement_annual")),
        ("Income Statement (Quarterly)", yf_data.get("income_statement_quarterly")),
        ("Balance Sheet (Annual)", yf_data.get("balance_sheet_annual")),
        ("Balance Sheet (Quarterly)", yf_data.get("balance_sheet_quarterly")),
        ("Cash Flow Statement (Annual)", yf_data.get("cashflow_statement_annual")),
        ("Cash Flow Statement (Quarterly)", yf_data.get("cashflow_statement_quarterly")),
    ]

    for title, payload in mapping:
        table_md = _json_to_markdown_table(payload)
        if table_md:
            sections.append(f"# {title}\n{table_md}")

    return "\n\n".join(sections)


def expand_financials_variable(security, annual_years: int, quarterly_count: int):
    """
    Resolve {{financials:yX:qY}} using edgar cache first (via get_edgar_data),
    then fall back to yfinance JSON stored on CF Security. Returns JSON formatted as string.
    """
    # 1) Try edgar cache via existing helper (may rely on cached files)
    cik = getattr(security, "cik", None)
    if cik:
        try:
            edgar_json = get_edgar_data(
                cik=cik,
                annual_years=annual_years,
                quarterly_count=quarterly_count,
                format="json",
            )
            if edgar_json:
                return edgar_json
        except Exception:
            # Fall through to yfinance
            pass

    # 2) Fallback to yfinance cached JSON
    yf_data = get_cached_yfinance_data(security, annual_years, quarterly_count)
    if any(yf_data.values()):
        import json
        return json.dumps(yf_data, indent=2)

    # 3) Placeholder if nothing available
    return '{"error": "financial data unavailable"}'


def get_edgar_data(
    cik: str,
    annual_years: int = 10,
    quarterly_count: int = 16,
    format: str = "json",
    statement_types: list = None
) -> str:
    """
    Fetch and return financial statements from SEC EDGAR filings using statement stitching.
    
    This method retrieves multiple filings and stitches them together to create
    a multi-period view of financial statements, supporting both annual (10-K) 
    and quarterly (10-Q) data.
    
    Args:
        cik: Company CIK identifier
        annual_years: Number of annual periods to retrieve (default: 10)
        quarterly_count: Number of quarterly periods to retrieve (default: 16)
        format: Output format - 'json', 'csv', or 'markdown' (default: 'json')
        statement_types: List of statement types to retrieve. 
                        Options: 'income', 'balance', 'cashflow', 'equity'
                        Default: all statements
    
    Returns:
        A single text string containing all requested financial statements
        in the specified format (json, csv, or markdown), with data from
        multiple periods stitched together.
    """
    from edgar import set_identity, Company, use_local_storage
    from edgar.xbrl import XBRLS
    import json as json_module

    # Enable edgartools disk caching (defaults to ~/.edgar)
    use_local_storage(True)

    if statement_types is None:
        statement_types = ['income', 'balance', 'cashflow', 'equity']
    
    # Validate format
    valid_formats = ['json', 'csv', 'markdown']
    if format not in valid_formats:
        raise ValueError(f"Format must be one of {valid_formats}, got '{format}'")

    set_identity("phalouvas@gmail.com")

    company = Company(cik)
    
    # Dictionary to store all statement data
    all_data = {}

    # Helper function to convert statement to desired format
    def convert_statement_to_format(statement, stmt_name, format_type):
        try:
            df = statement.to_dataframe()
            
            if format_type == 'json':
                return {
                    'statement': stmt_name,
                    'periods': len(df.columns) if hasattr(df, 'columns') else 0,
                    'data': json_module.loads(df.to_json(orient='records'))
                }
            elif format_type == 'csv':
                return f"# {stmt_name}\n" + df.to_csv(index=True)
            elif format_type == 'markdown':
                return f"# {stmt_name}\n" + df.to_markdown(index=True)
        except Exception as e:
            return {
                'statement': stmt_name,
                'error': str(e)
            } if format_type == 'json' else f"# {stmt_name}\nError: {str(e)}\n"

    # ===== ANNUAL DATA =====
    if annual_years > 0:
        try:
            # Get multiple 10-K filings for annual statements
            annual_filings = company.get_filings(form="10-K").head(annual_years)
            
            if len(annual_filings) > 0:
                # Create stitched view across multiple annual filings
                xbrls_annual = XBRLS.from_filings(annual_filings)
                statements_annual = xbrls_annual.statements

                # Fetch and convert annual income statement
                if 'income' in statement_types:
                    try:
                        income_annual = statements_annual.income_statement(max_periods=annual_years)
                        all_data['income_statement_annual'] = convert_statement_to_format(
                            income_annual, 'Income Statement (Annual)', format
                        )
                    except Exception as e:
                        all_data['income_statement_annual'] = {
                            'statement': 'Income Statement (Annual)',
                            'error': str(e)
                        } if format == 'json' else f"# Income Statement (Annual)\nError: {str(e)}\n"

                # Fetch and convert annual balance sheet
                if 'balance' in statement_types:
                    try:
                        balance_annual = statements_annual.balance_sheet(max_periods=annual_years)
                        all_data['balance_sheet_annual'] = convert_statement_to_format(
                            balance_annual, 'Balance Sheet (Annual)', format
                        )
                    except Exception as e:
                        all_data['balance_sheet_annual'] = {
                            'statement': 'Balance Sheet (Annual)',
                            'error': str(e)
                        } if format == 'json' else f"# Balance Sheet (Annual)\nError: {str(e)}\n"

                # Fetch and convert annual cash flow statement
                if 'cashflow' in statement_types:
                    try:
                        cashflow_annual = statements_annual.cashflow_statement(max_periods=annual_years)
                        all_data['cashflow_statement_annual'] = convert_statement_to_format(
                            cashflow_annual, 'Cash Flow Statement (Annual)', format
                        )
                    except Exception as e:
                        all_data['cashflow_statement_annual'] = {
                            'statement': 'Cash Flow Statement (Annual)',
                            'error': str(e)
                        } if format == 'json' else f"# Cash Flow Statement (Annual)\nError: {str(e)}\n"

                # Fetch and convert statement of equity (if available)
                if 'equity' in statement_types:
                    try:
                        equity_annual = statements_annual.statement_of_equity(max_periods=annual_years)
                        all_data['equity_statement_annual'] = convert_statement_to_format(
                            equity_annual, 'Statement of Equity (Annual)', format
                        )
                    except Exception as e:
                        all_data['equity_statement_annual'] = {
                            'statement': 'Statement of Equity (Annual)',
                            'error': f"Statement not available: {str(e)}"
                        } if format == 'json' else f"# Statement of Equity (Annual)\nNot available: {str(e)}\n"
        except Exception as e:
            all_data['annual_error'] = {
                'error_type': 'Annual data retrieval failed',
                'message': str(e)
            } if format == 'json' else f"\n# Annual Data Error\n{str(e)}\n"

    # ===== QUARTERLY DATA =====
    if quarterly_count > 0:
        try:
            # Get multiple 10-Q filings for quarterly statements
            quarterly_filings = company.get_filings(form="10-Q").head(quarterly_count)
            
            if len(quarterly_filings) > 0:
                # Create stitched view across multiple quarterly filings
                xbrls_quarterly = XBRLS.from_filings(quarterly_filings)
                statements_quarterly = xbrls_quarterly.statements

                # Fetch and convert quarterly income statement
                if 'income' in statement_types:
                    try:
                        income_quarterly = statements_quarterly.income_statement(max_periods=quarterly_count)
                        all_data['income_statement_quarterly'] = convert_statement_to_format(
                            income_quarterly, 'Income Statement (Quarterly)', format
                        )
                    except Exception as e:
                        all_data['income_statement_quarterly'] = {
                            'statement': 'Income Statement (Quarterly)',
                            'error': str(e)
                        } if format == 'json' else f"# Income Statement (Quarterly)\nError: {str(e)}\n"

                # Fetch and convert quarterly balance sheet
                if 'balance' in statement_types:
                    try:
                        balance_quarterly = statements_quarterly.balance_sheet(max_periods=quarterly_count)
                        all_data['balance_sheet_quarterly'] = convert_statement_to_format(
                            balance_quarterly, 'Balance Sheet (Quarterly)', format
                        )
                    except Exception as e:
                        all_data['balance_sheet_quarterly'] = {
                            'statement': 'Balance Sheet (Quarterly)',
                            'error': str(e)
                        } if format == 'json' else f"# Balance Sheet (Quarterly)\nError: {str(e)}\n"

                # Fetch and convert quarterly cash flow statement
                if 'cashflow' in statement_types:
                    try:
                        cashflow_quarterly = statements_quarterly.cashflow_statement(max_periods=quarterly_count)
                        all_data['cashflow_statement_quarterly'] = convert_statement_to_format(
                            cashflow_quarterly, 'Cash Flow Statement (Quarterly)', format
                        )
                    except Exception as e:
                        all_data['cashflow_statement_quarterly'] = {
                            'statement': 'Cash Flow Statement (Quarterly)',
                            'error': str(e)
                        } if format == 'json' else f"# Cash Flow Statement (Quarterly)\nError: {str(e)}\n"

                # Fetch and convert quarterly statement of equity (if available)
                if 'equity' in statement_types:
                    try:
                        equity_quarterly = statements_quarterly.statement_of_equity(max_periods=quarterly_count)
                        all_data['equity_statement_quarterly'] = convert_statement_to_format(
                            equity_quarterly, 'Statement of Equity (Quarterly)', format
                        )
                    except Exception as e:
                        all_data['equity_statement_quarterly'] = {
                            'statement': 'Statement of Equity (Quarterly)',
                            'error': f"Statement not available: {str(e)}"
                        } if format == 'json' else f"# Statement of Equity (Quarterly)\nNot available: {str(e)}\n"
        except Exception as e:
            all_data['quarterly_error'] = {
                'error_type': 'Quarterly data retrieval failed',
                'message': str(e)
            } if format == 'json' else f"\n# Quarterly Data Error\n{str(e)}\n"

    # Combine all data into a single text string
    if format == 'json':
        result = json_module.dumps(all_data, indent=2)
    elif format == 'csv':
        result = "\n".join([
            stmt_data if isinstance(stmt_data, str) else f"# {stmt_data.get('statement', 'Unknown')}\n"
            for stmt_data in all_data.values()
        ])
    elif format == 'markdown':
        result = "\n\n".join([
            stmt_data if isinstance(stmt_data, str) else f"## {stmt_data.get('statement', 'Unknown')}\n\nError: {stmt_data.get('error', 'Unknown error')}"
            for stmt_data in all_data.values()
        ])

    return result


def get_edgar_section(
    cik: str,
    form_type: str = "10-K",
    year_or_index: int = -1,
    quarter: str = None,
    section: str = None,
    aggregate_all: bool = False,
    max_chars: int = 200000
) -> str:
    """
    Fetch specific narrative sections from SEC Edgar filings for qualitative AI analysis.
    
    This extracts qualitative text (Risk Factors, MD&A, Business Description) rather than
    structured financial data. Each filing includes metadata headers for context.
    
    Args:
        cik: Company CIK identifier
        form_type: Filing type - '10-K' (annual), '10-Q' (quarterly), or '8-K' (current reports)
        year_or_index: Negative for relative (-1 = latest, -2 = previous), 
                      Positive 4-digit for absolute year (2024, 2023, etc.)
        quarter: Quarter specification for 10-Q ('Q1', 'Q2', 'Q3') - optional
        section: Section to extract - 'risk', 'mda', 'business', 'legal', 'all', or None
                None = default selection (risk+mda+business for 10-K/10-Q)
        aggregate_all: For 8-K with absolute year, aggregate ALL 8-Ks from that year
                      For relative index, aggregates latest 3
        max_chars: Maximum characters to return (default 200K, truncates with notice)
    
    Returns:
        Plain text content with metadata headers, or error message
        
    Examples:
        get_edgar_section('0000320193', '10-K', -1, section='risk')  # Latest 10-K risks
        get_edgar_section('0000320193', '10-Q', 2024, quarter='Q2', section='mda')
        get_edgar_section('0000320193', '8-K', 2024, aggregate_all=True)  # All 2024 8-Ks
        get_edgar_section('0000320193', '10-K', -1)  # Latest 10-K default sections
    """
    from edgar import set_identity, Company, use_local_storage
    import frappe
    
    # Enable edgartools disk caching
    use_local_storage(True)
    set_identity("phalouvas@gmail.com")
    
    # Section keyword mapping to TenK/TenQ object properties
    section_map = {
        'risk': 'risk_factors',
        'mda': 'management_discussion',
        'business': 'business',
        'legal': 'legal_proceedings',
        'all': None  # Special case - return full text
    }
    
    try:
        company = Company(cik)
        content_parts = []
        
        # Determine if we're dealing with relative index or absolute year
        is_relative = year_or_index < 0 or year_or_index < 1000
        
        if form_type == '8-K':
            # 8-K aggregation logic
            if is_relative:
                # Relative: get latest N filings
                count = abs(year_or_index) if year_or_index < 0 else 3
                filings = company.get_filings(form="8-K").head(count)
            else:
                # Absolute year: get all 8-Ks from that year
                all_8k_filings = company.get_filings(form="8-K")
                filings = [f for f in all_8k_filings if f.filing_date.year == year_or_index]
                
                if not filings:
                    return f"[No 8-K filings found for year {year_or_index}]"
            
            # Process each 8-K filing
            for filing in filings:
                try:
                    eightk = filing.obj()
                    
                    # Add metadata header
                    metadata = f"**8-K Filing**\n"
                    metadata += f"Filed: {filing.filing_date}\n"
                    if hasattr(filing, 'accession_no'):
                        metadata += f"Accession: {filing.accession_no}\n"
                    metadata += f"\n"
                    
                    # Extract all reported items
                    items_content = []
                    if hasattr(eightk, 'items') and eightk.items:
                        for item in eightk.items:
                            try:
                                item_text = eightk[item]
                                if item_text:
                                    items_content.append(f"**{item}**\n{item_text}")
                            except Exception:
                                continue
                    
                    if items_content:
                        content_parts.append(metadata + "\n\n".join(items_content))
                    
                except Exception as e:
                    # Log but continue with other filings
                    frappe.log_error(f"Error processing 8-K {filing.accession_no}: {str(e)}", "Edgar 8-K Processing")
                    continue
            
        else:
            # 10-K or 10-Q logic
            if is_relative:
                # Relative index: get the Nth most recent filing
                index = abs(year_or_index) - 1 if year_or_index < 0 else 0
                all_filings = company.get_filings(form=form_type)
                # Filter out amendments (10-K/A, 10-Q/A) to get full documents
                filings = [f for f in all_filings if f.form == form_type]
                
                # For 10-Q with quarter, filter by quarter if possible
                if form_type == "10-Q" and quarter:
                    # This is a simplification - proper quarter matching would require
                    # checking filing dates or period end dates
                    pass  # Use all 10-Q filings for now
                
                if len(filings) <= index:
                    return f"[Insufficient filings: requested index {index} but only {len(filings)} available]"
                
                filing = filings[index]
                
            else:
                # Absolute year: get filing from specific year
                all_filings = company.get_filings(form=form_type)
                # Filter out amendments (10-K/A, 10-Q/A) to get full documents
                all_filings = [f for f in all_filings if f.form == form_type]
                
                # Filter by year
                year_filings = [f for f in all_filings if f.filing_date.year == year_or_index]
                
                if not year_filings:
                    return f"[No {form_type} filing found for year {year_or_index}]"
                
                # For 10-Q with quarter, try to match quarter
                if form_type == "10-Q" and quarter:
                    # Simple quarter matching by filing date month ranges
                    quarter_months = {
                        'Q1': (4, 5, 6),      # Filed Apr-Jun
                        'Q2': (7, 8, 9),      # Filed Jul-Sep
                        'Q3': (10, 11, 12),   # Filed Oct-Dec
                    }
                    
                    if quarter in quarter_months:
                        months = quarter_months[quarter]
                        quarter_filings = [f for f in year_filings if f.filing_date.month in months]
                        if quarter_filings:
                            filing = quarter_filings[0]  # Most recent in that quarter range
                        else:
                            return f"[No 10-Q filing found for {year_or_index} {quarter}]"
                    else:
                        filing = year_filings[0]  # Latest from that year
                else:
                    filing = year_filings[0]  # Latest from that year
            
            # Get the data object (TenK or TenQ)
            data_obj = filing.obj()
            
            # Add metadata header
            metadata = f"**{form_type} Filing**\n"
            metadata += f"Filed: {filing.filing_date}\n"
            if hasattr(filing, 'period_end_date'):
                metadata += f"Period: {filing.period_end_date}\n"
            if hasattr(filing, 'accession_no'):
                metadata += f"Accession: {filing.accession_no}\n"
            metadata += f"\n"
            
            content_parts.append(metadata)
            
            # Extract sections based on parameter
            if section == 'all':
                # Return full filing text
                full_text = filing.text()
                content_parts.append(full_text)
                
            elif section in section_map and section_map[section] is not None:
                # Extract specific section
                prop_name = section_map[section]
                if hasattr(data_obj, prop_name):
                    section_content = getattr(data_obj, prop_name)
                    if section_content:
                        section_title = prop_name.replace('_', ' ').title()
                        content_parts.append(f"# {section_title}\n\n{section_content}")
                    else:
                        content_parts.append(f"[{prop_name} section not available in this filing]")
                else:
                    content_parts.append(f"[{prop_name} section not available in this filing]")
                    
            else:
                # Default: combine risk + mda + business for comprehensive overview
                default_sections = [
                    ('risk_factors', 'Risk Factors'),
                    ('management_discussion', 'Management Discussion & Analysis'),
                    ('business', 'Business Description')
                ]
                
                for prop_name, title in default_sections:
                    if hasattr(data_obj, prop_name):
                        section_content = getattr(data_obj, prop_name)
                        if section_content:
                            content_parts.append(f"# {title}\n\n{section_content}")
        
        # Combine all content
        full_content = "\n\n---\n\n".join(content_parts)
        
        # Apply character limit with truncation notice
        if len(full_content) > max_chars:
            full_content = full_content[:max_chars] + f"\n\n[Content truncated at {max_chars:,} characters. Original length: {len(full_content):,} characters]"
        
        # Log token estimate
        estimated_tokens = len(full_content) // 4
        if frappe:
            frappe.logger().info(f"Edgar section extraction: {form_type} for CIK {cik}, ~{estimated_tokens:,} tokens")
        
        return full_content if full_content.strip() else f"[No content extracted from {form_type} filing]"
        
    except Exception as e:
        error_msg = f"[Error fetching {form_type}: {str(e)}]"
        if frappe:
            frappe.log_error(f"Edgar section extraction failed for CIK {cik}, form {form_type}: {str(e)}", "Edgar Section Extraction Error")
        return error_msg


def expand_edgar_section_variable(security, form_type: str, year_or_index: str, section: str = None, quarter: str = None):
    """
    Wrapper to expand {{edgar:...}} variables in chat prompts.
    
    Extracts CIK from security, parses parameters, and calls get_edgar_section.
    
    Args:
        security: CF Security document
        form_type: Filing type (10-K, 10-Q, 8-K)
        year_or_index: String representation of year (2024) or relative index (-1, -2)
        section: Optional section keyword (risk, mda, business, legal, all)
        quarter: Optional quarter for 10-Q (Q1, Q2, Q3)
    
    Returns:
        Extracted text content or error placeholder
    """
    import frappe
    
    # Check for CIK
    cik = getattr(security, "cik", None)
    if not cik:
        return "[CIK required for edgar variable - fetch CIK using Actions → Fetch CIK]"
    
    try:
        # Parse year_or_index
        year_or_index_int = int(year_or_index)
        
        # For 8-K with 4-digit year, aggregate all filings from that year
        aggregate_all = (form_type == "8-K" and year_or_index_int >= 1000)
        
        # Call the main function
        result = get_edgar_section(
            cik=cik,
            form_type=form_type,
            year_or_index=year_or_index_int,
            quarter=quarter,
            section=section,
            aggregate_all=aggregate_all
        )
        
        return result
        
    except ValueError:
        return f"[Invalid year/index format: {year_or_index}]"
    except Exception as e:
        frappe.log_error(f"Edgar variable expansion failed for {security.name}: {str(e)}", "Edgar Variable Expansion Error")
        return f"[SEC filing not found: {form_type} {year_or_index}]"

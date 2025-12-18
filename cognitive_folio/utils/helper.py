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
    from edgar import set_identity, Company
    from edgar.xbrl import XBRLS
    import json as json_module

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

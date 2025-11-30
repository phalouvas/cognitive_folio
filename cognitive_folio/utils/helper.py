import json
import re
import frappe

def _format_num(value, currency=None):
    try:
        if value is None:
            return "-"
        v = float(value)
        if currency:
            symbols = {'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥', 'CNY': '¥', 'HKD': 'HK$', 'AUD': 'A$', 'CAD': 'C$'}
            sym = symbols.get(currency, f"{currency} ")
            return f"{sym}{v:,.2f}"
        return f"{v:,.2f}"
    except Exception:
        return str(value) if value is not None else "-"

def _pick_security_currency(security_name: str) -> str:
    try:
        sec = frappe.get_doc("CF Security", security_name)
        return getattr(sec, 'currency', None) or 'USD'
    except Exception:
        return 'USD'

def _get_periods(security_name: str, period_type: str, limit: int):
    return frappe.get_all(
        "CF Financial Period",
        filters={"security": security_name, "period_type": period_type},
        fields=[
            "name", "fiscal_year", "fiscal_quarter", "period_end_date",
            "total_revenue", "net_income", "diluted_eps",
            "gross_margin", "operating_margin", "net_margin",
            "roe", "current_ratio", "free_cash_flow"
        ],
        order_by="fiscal_year DESC, fiscal_quarter DESC",
        limit=limit
    )

def _format_comparison_block(security_name: str, key_a: str, key_b: str) -> str:
    """Build a markdown comparison between two keyed periods.

    Keys: latest_annual, previous_annual, annual_minus_2,
          latest_quarterly, previous_quarterly, yoy_quarterly
    """
    currency = _pick_security_currency(security_name)

    def resolve_key(key: str):
        if key in {"latest_annual", "previous_annual", "annual_minus_2"}:
            periods = _get_periods(security_name, "Annual", 3)
            idx_map = {"latest_annual": 0, "previous_annual": 1, "annual_minus_2": 2}
            idx = idx_map.get(key, 0)
            return periods[idx] if len(periods) > idx else None
        if key in {"latest_quarterly", "previous_quarterly"}:
            periods = _get_periods(security_name, "Quarterly", 2)
            idx_map = {"latest_quarterly": 0, "previous_quarterly": 1}
            idx = idx_map.get(key, 0)
            return periods[idx] if len(periods) > idx else None
        if key == "yoy_quarterly":
            latest = _get_periods(security_name, "Quarterly", 1)
            if not latest:
                return None
            latest = latest[0]
            comp = frappe.db.get_value(
                "CF Financial Period",
                {
                    "security": security_name,
                    "period_type": "Quarterly",
                    "fiscal_year": int(latest.fiscal_year) - 1,
                    "fiscal_quarter": latest.fiscal_quarter,
                },
                [
                    "name", "fiscal_year", "fiscal_quarter", "period_end_date",
                    "total_revenue", "net_income", "diluted_eps",
                    "gross_margin", "operating_margin", "net_margin",
                    "roe", "current_ratio", "free_cash_flow"
                ],
                as_dict=True,
            )
            return (latest, comp) if comp else (latest, None)
        return None

    if key_a == "yoy_quarterly":
        a, b = resolve_key("yoy_quarterly") or (None, None)
    else:
        a = resolve_key(key_a)
        b = resolve_key(key_b)

    if not a or not b:
        return "Comparison data unavailable."

    def label(p):
        lbl = str(p.fiscal_year)
        if p.fiscal_quarter:
            lbl += f" {p.fiscal_quarter}"
        return lbl

    rows = []
    def add_row(metric, va, vb, is_pct=False, currency_flag=False):
        if is_pct:
            fa = f"{(va or 0):.2f}%" if va is not None else "-"
            fb = f"{(vb or 0):.2f}%" if vb is not None else "-"
        elif currency_flag:
            fa = _format_num(va, currency)
            fb = _format_num(vb, currency)
        else:
            fa = _format_num(va)
            fb = _format_num(vb)
        rows.append((metric, fa, fb))

    add_row("Revenue", a.total_revenue, b.total_revenue, currency_flag=True)
    add_row("Net Income", a.net_income, b.net_income, currency_flag=True)
    add_row("EPS (Diluted)", a.diluted_eps, b.diluted_eps)
    add_row("Gross Margin", a.gross_margin, b.gross_margin, is_pct=True)
    add_row("Operating Margin", a.operating_margin, b.operating_margin, is_pct=True)
    add_row("Net Margin", a.net_margin, b.net_margin, is_pct=True)
    add_row("ROE", a.roe, b.roe, is_pct=True)
    add_row("Current Ratio", a.current_ratio, b.current_ratio)
    add_row("Free Cash Flow", a.free_cash_flow, b.free_cash_flow, currency_flag=True)

    lines = [f"Period A: {label(a)} | Period B: {label(b)}", "", "Metric | A | B", "---|---|---"]
    for metric, va, vb in rows:
        lines.append(f"{metric} | {va} | {vb}")
    return "\n".join(lines)

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
        # Special handler for periods tags: periods:annual:5[:format] or periods:compare:case1:case2
        if variable_name.startswith('periods:'):
            parts = variable_name.split(':')
            # periods:compare:...
            if len(parts) >= 2 and parts[1].lower() == 'compare':
                # Expected: periods:compare:key1:key2
                if len(parts) >= 4:
                    key1 = parts[2]
                    key2 = parts[3]
                    return _format_comparison_block(doc.name, key1, key2)
                return ""
            # periods:<type>:<n>[:format]
            if len(parts) >= 3:
                period_type = parts[1].strip().title()  # Annual/Quarterly/TTM
                try:
                    num = int(parts[2])
                except Exception:
                    num = 5
                fmt = parts[3].lower() if len(parts) >= 4 else 'markdown'
                # Import formatter from financial period module to avoid duplication
                from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import format_periods_for_ai
                return format_periods_for_ai(doc.name, period_type=period_type, num_periods=num, include_growth=True, format=fmt)
            return ""

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

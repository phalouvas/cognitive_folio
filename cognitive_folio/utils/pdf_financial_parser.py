"""
PDF Financial Statement Parser for 10-Q/10-K SEC Filings

Extracts financial data from uploaded PDF documents and creates CF Financial Period records.
Leverages pdfplumber for table detection and text extraction.
"""

import frappe
import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from decimal import Decimal


def parse_financial_pdf(
    security: str,
    file_path: str,
    period_type: str = "Annual",
    data_source: str = "PDF Upload"
) -> Dict:
    """
    Parse a financial statement PDF and extract structured data.
    
    Args:
        security: Symbol/ticker of the security
        file_path: Full path to the PDF file
        period_type: "Annual" or "Quarterly"
        data_source: Source identifier (default: "PDF Upload")
    
    Returns:
        Dict with keys: success, extracted_periods, created_count, error
    """
    # Normalize period_type to allowed values
    if isinstance(period_type, str):
        pt = period_type.strip().lower()
        if pt in ("annual", "year", "y", "fy", "yearly"):
            period_type = "Annual"
        elif pt in ("quarterly", "q", "fq", "quarter"):
            period_type = "Quarterly"
        elif pt == "ttm":
            period_type = "TTM"
    # Normalize data_source to allowed values
    allowed_sources = {"Yahoo Finance", "Manual Entry", "PDF Upload", "SEC Edgar", "Other API"}
    if data_source not in allowed_sources:
        data_source = "PDF Upload"

    # Try to import PDF libraries
    pdfplumber_available = False
    pypdf2_available = False
    
    try:
        import pdfplumber
        pdfplumber_available = True
    except ImportError:
        pass
    
    try:
        import PyPDF2
        pypdf2_available = True
    except ImportError:
        pass
    
    if not pdfplumber_available and not pypdf2_available:
        return {
            "success": False,
            "error": "No PDF library available. Install: bench pip install pdfplumber PyPDF2",
            "extracted_periods": [],
            "created_count": 0
        }
    
    # Resolve security name (accepts Doc or symbol string)
    try:
        security_name = security.name  # type: ignore[attr-defined]
    except Exception:
        security_name = str(security)

    try:
        extracted_periods = []
        all_tables = []
        
        # Try pdfplumber first (best for table-based PDFs)
        pdfplumber_tables = []
        if pdfplumber_available:
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        try:
                            tables = page.extract_tables()
                            if tables:
                                pdfplumber_tables.extend(tables)
                        except Exception:
                            pass
            except Exception:
                pass
        
        # Try PyPDF2 text-based extraction (often better for text-heavy PDFs)
        pypdf2_tables = []
        if pypdf2_available:
            try:
                pypdf2_tables = _extract_tables_from_text(file_path, period_type)
            except Exception:
                pass
        
        # Use whichever extraction found more tables
        # PyPDF2 text parsing is often better for financial documents
        if len(pypdf2_tables) > 0:
            all_tables = pypdf2_tables
        elif len(pdfplumber_tables) > 0:
            all_tables = pdfplumber_tables
        
        if not all_tables:
            return {
                "success": False,
                "error": f"No financial data detected in PDF (tried {('pdfplumber, ' if pdfplumber_available else '') + ('PyPDF2' if pypdf2_available else '')})",
                "extracted_periods": [],
                "created_count": 0
            }
        
        # Attempt to identify financial statement tables
        
        income_statement = _find_income_statement(all_tables)
        balance_sheet = _find_balance_sheet(all_tables)
        cash_flow = _find_cash_flow_statement(all_tables)
        
        
        
        # Extract data from identified tables
        if income_statement:
            periods = _extract_periods_from_income_statement(income_statement, period_type)
            extracted_periods.extend(periods)
            
            if balance_sheet:
                _merge_balance_sheet_data(extracted_periods, balance_sheet)
            
            if cash_flow:
                _merge_cash_flow_data(extracted_periods, cash_flow)
        
        # Create CF Financial Period records
        created_count = 0
        errors = []
        
        for period_data in extracted_periods:
            try:
                # Build filter dict for period lookup
                period_filter = {
                    "security": security_name,
                    "period_type": period_type,
                    "fiscal_year": period_data["fiscal_year"]
                }
                
                if period_type == "Quarterly" and period_data.get("fiscal_quarter"):
                    period_filter["fiscal_quarter"] = period_data["fiscal_quarter"]
                
                # Check if period already exists with higher quality
                existing = frappe.db.get_value(
                    "CF Financial Period",
                    period_filter,
                    ["name", "data_quality_score"],
                    as_dict=True
                )
                
                # PDF uploads get quality score of 90 (higher than Yahoo's 85, lower than verified 100)
                pdf_quality_score = 90
                
                if existing and existing.data_quality_score >= pdf_quality_score:
                    # Skip if existing data is higher quality
                    continue
                
                # Create or update period
                if existing:
                    doc = frappe.get_doc("CF Financial Period", existing.name)
                else:
                    doc = frappe.new_doc("CF Financial Period")
                    doc.security = security_name
                    doc.period_type = period_type
                    doc.fiscal_year = period_data["fiscal_year"]
                    
                    # Calculate period_end_date
                    from datetime import date
                    if period_type == "Quarterly" and period_data.get("fiscal_quarter"):
                        doc.fiscal_quarter = period_data["fiscal_quarter"]
                        # Quarter end dates (Mar 31, Jun 30, Sep 30, Dec 31)
                        quarter_months = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}
                        month = quarter_months.get(period_data["fiscal_quarter"], 12)
                        # Last day of the month
                        if month in [1, 3, 5, 7, 8, 10, 12]:
                            day = 31
                        elif month in [4, 6, 9, 11]:
                            day = 30
                        else:  # February
                            day = 28
                        doc.period_end_date = date(period_data["fiscal_year"], month, day)
                    else:
                        # Annual period ends on December 31st
                        doc.period_end_date = date(period_data["fiscal_year"], 12, 31)
                
                # Set financial data
                doc.data_source = data_source
                doc.data_quality_score = pdf_quality_score
                
                # Income statement fields
                _set_if_present(doc, "total_revenue", period_data)
                _set_if_present(doc, "cost_of_revenue", period_data)
                _set_if_present(doc, "operating_expenses", period_data)
                _set_if_present(doc, "operating_income", period_data)
                _set_if_present(doc, "interest_expense", period_data)
                _set_if_present(doc, "net_income", period_data)
                _set_if_present(doc, "ebitda", period_data)
                
                # Balance sheet fields
                _set_if_present(doc, "total_assets", period_data)
                _set_if_present(doc, "total_liabilities", period_data)
                _set_if_present(doc, "shareholders_equity", period_data)
                _set_if_present(doc, "total_debt", period_data)
                _set_if_present(doc, "cash_and_equivalents", period_data)
                
                # Cash flow fields
                _set_if_present(doc, "operating_cash_flow", period_data)
                _set_if_present(doc, "capital_expenditures", period_data)
                _set_if_present(doc, "free_cash_flow", period_data)
                
                doc.save()
                created_count += 1
                
            except Exception as e:
                import traceback
                period_str = f"{period_data.get('fiscal_year', 'unknown')}"
                if period_data.get('fiscal_quarter'):
                    period_str += f" {period_data['fiscal_quarter']}"
                error_details = f"Period: {period_str}\nError: {str(e)}\nTraceback:\n{traceback.format_exc()}"
                errors.append(f"Error creating period {period_str}: {str(e)}")
                frappe.log_error(
                    title=f"PDF Period Import Error: {security}",
                    message=error_details
                )
        
        frappe.db.commit()
        
        return {
            "success": True,
            "extracted_periods": len(extracted_periods),
            "created_count": created_count,
            "errors": errors if errors else None
        }
        
    except Exception as e:
        frappe.log_error(
            title=f"PDF Financial Parser Error: {security}",
            message=str(e)
        )
        return {
            "success": False,
            "error": str(e),
            "extracted_periods": 0,
            "created_count": 0
        }


def _extract_tables_from_text(file_path: str, period_type: str) -> List:
    """
    Extract financial data from text-based PDF using PyPDF2.
    Converts text into table-like structure for parsing.
    """
    import PyPDF2
    tables = []
    pages_checked = 0
    pages_with_financials = 0
    
    
    
    # Open file and keep it open while reading
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        
        # Search for financial statement pages
        for page_num in range(len(reader.pages)):
            pages_checked += 1
            try:
                text = reader.pages[page_num].extract_text()
                if not text:
                    continue
                
                text_lower = text.lower()
                
                # Look for consolidated statements of operations/income
                if ('total net sales' in text_lower or 'net revenue' in text_lower) and '$' in text:
                    pages_with_financials += 1
                    # Try to parse as income statement
                    table = _parse_text_as_table(text, 'income')
                    if table:
                        tables.append(table)
                
                # Look for balance sheet
                elif 'total assets' in text_lower and 'total liabilities' in text_lower:
                    pages_with_financials += 1
                    table = _parse_text_as_table(text, 'balance')
                    if table:
                        tables.append(table)
                
                # Look for cash flow
                elif 'cash flow' in text_lower and 'operating activities' in text_lower:
                    pages_with_financials += 1
                    table = _parse_text_as_table(text, 'cashflow')
                    if table:
                        tables.append(table)
            except Exception:
                continue
    
    
    return tables


def _parse_text_as_table(text: str, statement_type: str) -> Optional[List]:
    """
    Parse text into table-like structure.
    Looks for financial line items followed by amounts.
    """
    lines = text.split('\n')
    table = []
    
    # Build header row from years found in text
    header = ['']
    years_found = re.findall(r'\b(20\d{2})\b', text)
    if len(years_found) >= 2:
        # Get unique years in order
        unique_years = []
        for year in years_found:
            if year not in unique_years:
                unique_years.append(year)
        header.extend(unique_years[:3])  # Max 3 years
        table.append(header)
    else:
        return None
    
    # Parse financial line items
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        
        # Look for lines with financial data (has $ or numbers in millions/billions)
        if '$' in line_clean or re.search(r'\d+,\d+', line_clean):
            # Extract label and values
            # Pattern: "Label $ 123,456 $ 234,567 $ 345,678"
            parts = re.split(r'\$|\s{2,}', line_clean)
            if len(parts) >= 2:
                row = [parts[0].strip()]
                
                # Extract numeric values
                for part in parts[1:]:
                    # Clean and try to extract number
                    cleaned = part.strip().replace(',', '').replace('$', '')
                    if cleaned and cleaned[0].isdigit():
                        row.append(cleaned.split()[0])
                
                if len(row) >= 2:  # Has label and at least one value
                    table.append(row)
    
    return table if len(table) > 1 else None


def _find_income_statement(tables: List) -> Optional[List]:
    """Identify income statement table based on keywords.
    
    Supports international variations and different terminology.
    """
    
    
    keywords = [
        "revenue", "sales", "turnover", "income", "earnings",
        "total revenue", "net revenue", "net sales", "total sales",
        "cost of revenue", "cost of sales", "cost of goods", "cogs",
        "gross profit", "gross margin",
        "operating income", "operating profit", "ebit", "ebitda",
        "net income", "net profit", "net earnings", "profit for",
        "income statement", "statement of operations", "statement of income",
        "profit and loss", "p&l", "comprehensive income"
    ]
    
    for table in tables:
        if not table or len(table) < 2:
            continue
        
        # Check header row and first few rows for keywords
        text_sample = " ".join([
            " ".join([str(cell).lower() for cell in row if cell])
            for row in table[:8]  # Check more rows
        ])
        
        # Count keyword matches
        matches = sum(1 for kw in keywords if kw in text_sample)
        
        if matches >= 2:  # Reduced threshold for international compatibility
            return table

    return None


def _find_balance_sheet(tables: List) -> Optional[List]:
    """Identify balance sheet table based on keywords.
    
    Supports international variations and different terminology.
    """
    keywords = [
        "assets", "liabilities", "equity", "capital",
        "balance sheet", "statement of financial position", "financial position",
        "current assets", "non-current assets", "fixed assets",
        "current liabilities", "non-current liabilities",
        "stockholders", "shareholders", "owners equity",
        "total assets", "total liabilities",
        "total debt", "long-term debt", "short-term debt"
    ]
    
    for table in tables:
        if not table or len(table) < 2:
            continue
        
        text_sample = " ".join([
            " ".join([str(cell).lower() for cell in row if cell])
            for row in table[:8]
        ])
        
        matches = sum(1 for kw in keywords if kw in text_sample)
        
        if matches >= 2:
            return table
    
    return None


def _find_cash_flow_statement(tables: List) -> Optional[List]:
    """Identify cash flow statement table based on keywords.
    
    Supports international variations and different terminology.
    """
    keywords = [
        "cash flow", "cash flows", "statement of cash flow",
        "operating activities", "operating cash", "cash from operations",
        "investing activities", "investing cash",
        "financing activities", "financing cash",
        "capital expenditures", "capex", "capital expenditure",
        "free cash flow", "fcf",
        "net increase", "net decrease", "net change"
    ]
    
    for table in tables:
        if not table or len(table) < 2:
            continue
        
        text_sample = " ".join([
            " ".join([str(cell).lower() for cell in row if cell])
            for row in table[:8]
        ])
        
        matches = sum(1 for kw in keywords if kw in text_sample)
        
        if matches >= 2:
            return table
    
    return None


def _extract_periods_from_income_statement(table: List, period_type: str) -> List[Dict]:
    """
    Extract period columns and financial data from income statement table.
    
    Returns list of dicts, each representing one period with its data.
    """
    if not table or len(table) < 2:
        return []
    
    # First row typically contains period labels
    header_row = [str(cell).strip() if cell else "" for cell in table[0]]
    
    # Identify period columns (skip first column which is usually labels)
    period_columns = []
    for idx, cell in enumerate(header_row[1:], start=1):
        period_info = _parse_period_label(cell, period_type)
        if period_info:
            period_columns.append({
                "index": idx,
                "fiscal_year": period_info["fiscal_year"],
                "fiscal_quarter": period_info.get("fiscal_quarter")
            })
    
    if not period_columns:
        # No valid periods found
        return []
    
    # Initialize period data structures
    periods = [{
        "fiscal_year": col["fiscal_year"],
        "fiscal_quarter": col["fiscal_quarter"],
        "column_index": col["index"]
    } for col in period_columns]
    
    # Extract financial metrics from rows
    for row in table[1:]:
        if not row:
            continue
        
        label = str(row[0]).strip().lower() if row[0] else ""
        
        # Map label to field name
        field_name = _map_label_to_field(label, "income_statement")
        
        if field_name:
            # Extract values for each period column
            for period in periods:
                col_idx = period["column_index"]
                if col_idx < len(row):
                    value = _parse_financial_value(row[col_idx])
                    if value is not None:
                        period[field_name] = value
    
    return periods


def _merge_balance_sheet_data(periods: List[Dict], table: List):
    """Merge balance sheet data into existing period records."""
    if not table or len(table) < 2 or not periods:
        return
    
    header_row = [str(cell).strip() if cell else "" for cell in table[0]]
    
    for row in table[1:]:
        if not row:
            continue
        
        label = str(row[0]).strip().lower() if row[0] else ""
        field_name = _map_label_to_field(label, "balance_sheet")
        
        if field_name:
            # Try to match values to periods by column position
            for idx, period in enumerate(periods):
                col_idx = idx + 1  # Skip label column
                if col_idx < len(row):
                    value = _parse_financial_value(row[col_idx])
                    if value is not None:
                        period[field_name] = value


def _merge_cash_flow_data(periods: List[Dict], table: List):
    """Merge cash flow data into existing period records."""
    if not table or len(table) < 2 or not periods:
        return
    
    for row in table[1:]:
        if not row:
            continue
        
        label = str(row[0]).strip().lower() if row[0] else ""
        field_name = _map_label_to_field(label, "cash_flow")
        
        if field_name:
            for idx, period in enumerate(periods):
                col_idx = idx + 1
                if col_idx < len(row):
                    value = _parse_financial_value(row[col_idx])
                    if value is not None:
                        period[field_name] = value


def _parse_period_label(label: str, period_type: str) -> Optional[Dict]:
    """
    Parse period label from table header.
    
    Returns dict with:
        - fiscal_year: int (e.g., 2024)
        - fiscal_quarter: str (e.g., "Q3") - only for Quarterly periods
    
    Examples:
        "2024" -> {"fiscal_year": 2024}
        "Q3 2024" -> {"fiscal_year": 2024, "fiscal_quarter": "Q3"}
        "December 31, 2024" -> {"fiscal_year": 2024}
        "Three Months Ended Sep 30, 2024" -> {"fiscal_year": 2024, "fiscal_quarter": "Q3"}
    """
    if not label:
        return None
    
    label = label.strip()
    
    # Match year
    year_match = re.search(r'\b(20\d{2})\b', label)
    if not year_match:
        return None
    
    year = int(year_match.group(1))
    result = {"fiscal_year": year}
    
    # Match quarter if quarterly
    if period_type == "Quarterly":
        quarter_patterns = [
            (r'\bq[1-4]\b', lambda m: f"Q{m.group(0)[1]}"),
            (r'\b(first|1st)\s+quarter\b', lambda m: "Q1"),
            (r'\b(second|2nd)\s+quarter\b', lambda m: "Q2"),
            (r'\b(third|3rd)\s+quarter\b', lambda m: "Q3"),
            (r'\b(fourth|4th)\s+quarter\b', lambda m: "Q4"),
            # Month-based detection (English)
            (r'\b(january|jan|february|feb|march|mar)\b', lambda m: "Q1"),
            (r'\b(april|apr|may|june|jun)\b', lambda m: "Q2"),
            (r'\b(july|jul|august|aug|september|sep|sept)\b', lambda m: "Q3"),
            (r'\b(october|oct|november|nov|december|dec)\b', lambda m: "Q4"),
            # Numeric month patterns (03/31, 31/03, etc.)
            (r'\b(01|02|03|1|2|3)[/-](\d{1,2}|31|30|29|28)[/-]', lambda m: "Q1"),
            (r'\b(04|05|06|4|5|6)[/-]', lambda m: "Q2"),
            (r'\b(07|08|09|7|8|9)[/-]', lambda m: "Q3"),
            (r'\b(10|11|12)[/-]', lambda m: "Q4"),
        ]
        
        for pattern, extractor in quarter_patterns:
            match = re.search(pattern, label.lower())
            if match:
                quarter = extractor(match)
                result["fiscal_quarter"] = quarter
                break
    
    return result


def _map_label_to_field(label: str, statement_type: str) -> Optional[str]:
    """Map row label to CF Financial Period field name."""
    label = label.lower()
    
    # Income statement mappings - supports international variations
    income_mappings = {
        "total_revenue": [
            "revenue", "total revenue", "net revenue", "revenues",
            "sales", "net sales", "total sales", "turnover", "total turnover",
            "income", "total income"
        ],
        "cost_of_revenue": [
            "cost of revenue", "cost of sales", "cost of goods sold", "cogs",
            "cost of goods", "direct costs", "production costs"
        ],
        "operating_expenses": [
            "operating expenses", "operating expense", "total operating expenses",
            "administrative expenses", "selling expenses", "general expenses",
            "sg&a", "sga", "opex"
        ],
        "operating_income": [
            "operating income", "income from operations", "operating profit",
            "operating result", "ebit", "profit from operations"
        ],
        "interest_expense": [
            "interest expense", "interest paid", "net interest expense",
            "finance costs", "financial expenses", "interest charges"
        ],
        "net_income": [
            "net income", "net earnings", "net profit", "earnings",
            "profit for the year", "profit for the period",
            "profit attributable", "net result", "bottom line"
        ],
        "ebitda": [
            "ebitda", "adjusted ebitda", "normalised ebitda", "normalized ebitda"
        ],
        "gross_profit": [
            "gross profit", "gross margin", "gross income"
        ]
    }
    
    # Balance sheet mappings - supports international variations
    balance_mappings = {
        "total_assets": [
            "total assets", "assets", "total asset"
        ],
        "current_assets": [
            "current assets", "current asset"
        ],
        "total_liabilities": [
            "total liabilities", "liabilities", "total liability"
        ],
        "current_liabilities": [
            "current liabilities", "current liability"
        ],
        "shareholders_equity": [
            "stockholders equity", "shareholders equity", "shareholder equity",
            "total equity", "equity", "owners equity", "capital",
            "equity attributable"
        ],
        "total_debt": [
            "total debt", "long-term debt", "debt", "borrowings",
            "total borrowings", "financial liabilities"
        ],
        "cash_and_equivalents": [
            "cash and cash equivalents", "cash and equivalents", "cash",
            "cash at bank", "cash on hand"
        ]
    }
    
    # Cash flow mappings - supports international variations
    cash_flow_mappings = {
        "operating_cash_flow": [
            "cash from operating activities", "operating cash flow",
            "cash flow from operations", "net cash from operating",
            "cash generated from operations"
        ],
        "investing_cash_flow": [
            "cash from investing activities", "investing cash flow",
            "net cash from investing", "cash used in investing"
        ],
        "financing_cash_flow": [
            "cash from financing activities", "financing cash flow",
            "net cash from financing", "cash used in financing"
        ],
        "capital_expenditures": [
            "capital expenditures", "capex", "capital expenditure",
            "purchases of property", "acquisition of assets",
            "payments for property", "investment in assets"
        ],
        "free_cash_flow": [
            "free cash flow", "fcf"
        ]
    }
    
    # Select appropriate mapping
    if statement_type == "income_statement":
        mappings = income_mappings
    elif statement_type == "balance_sheet":
        mappings = balance_mappings
    else:  # cash_flow
        mappings = cash_flow_mappings
    
    # Find matching field
    for field_name, keywords in mappings.items():
        for keyword in keywords:
            if keyword in label:
                return field_name
    
    return None


def _parse_financial_value(value) -> Optional[float]:
    """
    Parse financial value from table cell.
    
    Handles formats like:
        "1,234.5"
        "(123.4)" -> negative
        "$1.2B" -> billions
        "45.6M" -> millions
    """
    if value is None or value == "":
        return None
    
    value_str = str(value).strip()
    
    if not value_str or value_str == "-" or value_str.lower() in ["n/a", "na", "—"]:
        return None
    
    # Check for parentheses (negative)
    is_negative = False
    if value_str.startswith("(") and value_str.endswith(")"):
        is_negative = True
        value_str = value_str[1:-1]
    
    # Remove currency symbols (supports multiple currencies) and thousands separators
    # Support both comma and period as thousand separators
    value_str = re.sub(r'[$€£¥₹₽¢₩₪₨₦₱₡₴₸₹₺₼₽,\s]', '', value_str)
    
    # Handle European number format (period as thousand separator, comma as decimal)
    # If there are both comma and period, assume period is thousand separator
    if ',' in value_str and '.' in value_str:
        # Multiple separators - remove periods (thousand sep), convert comma to period (decimal)
        value_str = value_str.replace('.', '').replace(',', '.')
    elif ',' in value_str:
        # Only comma - check if it's likely a decimal or thousand separator
        parts = value_str.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            # Likely decimal (e.g., "1234,56")
            value_str = value_str.replace(',', '.')
        else:
            # Likely thousand separator (e.g., "1,234,567")
            value_str = value_str.replace(',', '')
    
    # Check for magnitude suffixes (support international variations)
    multiplier = 1.0
    if value_str.endswith(("B", "b", "bn", "BN", "Bn")):
        multiplier = 1_000_000_000
        value_str = re.sub(r'[Bb][Nn]?$', '', value_str)
    elif value_str.endswith(("M", "m", "mn", "MN", "Mn", "mil", "MIL")):
        multiplier = 1_000_000
        value_str = re.sub(r'([Mm][Nn]?|[Mm][Ii][Ll])$', '', value_str)
    elif value_str.endswith(("K", "k", "th", "TH", "Th")):
        multiplier = 1_000
        value_str = re.sub(r'([Kk]|[Tt][Hh])$', '', value_str)
    
    # Try to convert to float
    try:
        numeric_value = float(value_str) * multiplier
        return -numeric_value if is_negative else numeric_value
    except ValueError:
        return None


def _set_if_present(doc, field_name: str, data: Dict):
    """Set field on document if present in data dict."""
    if field_name in data:
        setattr(doc, field_name, data[field_name])


@frappe.whitelist()
def upload_and_parse_financial_pdf(security: str, file_url: str, period_type: str = "Annual"):
    """
    Frappe whitelisted method to parse PDF from uploaded file.
    
    Args:
        security: Security symbol/ticker
        file_url: File URL from Frappe file attachment
        period_type: "Annual" or "Quarterly"
    
    Returns:
        Dict with parsing results
    """
    try:
        # Build absolute file path from file_url
        import os
        file_path = file_url
        if file_url.startswith("/files/"):
            filename = os.path.basename(file_url)
            file_path = frappe.get_site_path("files", filename)
        elif file_url.startswith("/private/files/"):
            filename = os.path.basename(file_url)
            file_path = frappe.get_site_path("private", "files", filename)
        elif not os.path.isabs(file_url):
            # Fallback: treat as files path
            filename = os.path.basename(file_url)
            file_path = frappe.get_site_path("files", filename)
        
        # Parse the PDF
        result = parse_financial_pdf(
            security=security,
            file_path=file_path,
            period_type=period_type,
            data_source="PDF Upload"
        )
        
        if result["success"]:
            frappe.msgprint(
                f"Successfully imported {result['created_count']} periods from PDF",
                alert=True,
                indicator="green"
            )
        else:
            frappe.msgprint(
                f"Failed to parse PDF: {result.get('error', 'Unknown error')}",
                alert=True,
                indicator="red"
            )
        
        return result
        
    except Exception as e:
        frappe.log_error(
            title=f"PDF Upload Parse Error: {security}",
            message=str(e)
        )
        frappe.msgprint(
            f"Error processing PDF: {str(e)}",
            alert=True,
            indicator="red"
        )
        return {
            "success": False,
            "error": str(e)
        }

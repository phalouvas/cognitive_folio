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
    try:
        import pdfplumber
    except ImportError:
        return {
            "success": False,
            "error": "pdfplumber not installed. Run: bench pip install pdfplumber",
            "extracted_periods": [],
            "created_count": 0
        }
    
    try:
        extracted_periods = []
        
        with pdfplumber.open(file_path) as pdf:
            # Extract all tables from PDF
            all_tables = []
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    all_tables.extend(tables)
            
            if not all_tables:
                return {
                    "success": False,
                    "error": "No tables detected in PDF",
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
                # Check if period already exists with higher quality
                existing = frappe.db.get_value(
                    "CF Financial Period",
                    {
                        "security": security,
                        "period": period_data["period"],
                        "period_type": period_type
                    },
                    ["name", "data_quality_score"],
                    as_dict=True
                )
                
                # PDF uploads get quality score of 90 (higher than Yahoo's 70, lower than verified 100)
                pdf_quality_score = 90
                
                if existing and existing.data_quality_score >= pdf_quality_score:
                    # Skip if existing data is higher quality
                    continue
                
                # Create or update period
                if existing:
                    doc = frappe.get_doc("CF Financial Period", existing.name)
                else:
                    doc = frappe.new_doc("CF Financial Period")
                    doc.security = security
                    doc.period = period_data["period"]
                    doc.period_type = period_type
                
                # Set financial data
                doc.data_source = data_source
                doc.data_quality_score = pdf_quality_score
                
                # Income statement fields
                _set_if_present(doc, "revenue", period_data)
                _set_if_present(doc, "cost_of_revenue", period_data)
                _set_if_present(doc, "operating_expenses", period_data)
                _set_if_present(doc, "operating_income", period_data)
                _set_if_present(doc, "interest_expense", period_data)
                _set_if_present(doc, "net_income", period_data)
                _set_if_present(doc, "ebitda", period_data)
                _set_if_present(doc, "depreciation_amortization", period_data)
                
                # Balance sheet fields
                _set_if_present(doc, "total_assets", period_data)
                _set_if_present(doc, "total_liabilities", period_data)
                _set_if_present(doc, "stockholders_equity", period_data)
                _set_if_present(doc, "total_debt", period_data)
                _set_if_present(doc, "cash_and_equivalents", period_data)
                
                # Cash flow fields
                _set_if_present(doc, "operating_cash_flow", period_data)
                _set_if_present(doc, "capital_expenditures", period_data)
                _set_if_present(doc, "free_cash_flow", period_data)
                
                doc.save()
                created_count += 1
                
            except Exception as e:
                errors.append(f"Error creating period {period_data.get('period', 'unknown')}: {str(e)}")
                frappe.log_error(
                    title=f"PDF Period Import Error: {security}",
                    message=f"Period: {period_data.get('period')}\n{str(e)}"
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


def _find_income_statement(tables: List) -> Optional[List]:
    """Identify income statement table based on keywords."""
    keywords = [
        "revenue", "sales", "net income", "operating income",
        "cost of revenue", "gross profit", "income statement"
    ]
    
    for table in tables:
        if not table or len(table) < 2:
            continue
        
        # Check header row and first few rows for keywords
        text_sample = " ".join([
            " ".join([str(cell).lower() for cell in row if cell])
            for row in table[:5]
        ])
        
        # Count keyword matches
        matches = sum(1 for kw in keywords if kw in text_sample)
        
        if matches >= 3:  # Require at least 3 matches
            return table
    
    return None


def _find_balance_sheet(tables: List) -> Optional[List]:
    """Identify balance sheet table based on keywords."""
    keywords = [
        "assets", "liabilities", "equity", "balance sheet",
        "current assets", "stockholders", "total debt"
    ]
    
    for table in tables:
        if not table or len(table) < 2:
            continue
        
        text_sample = " ".join([
            " ".join([str(cell).lower() for cell in row if cell])
            for row in table[:5]
        ])
        
        matches = sum(1 for kw in keywords if kw in text_sample)
        
        if matches >= 3:
            return table
    
    return None


def _find_cash_flow_statement(tables: List) -> Optional[List]:
    """Identify cash flow statement table based on keywords."""
    keywords = [
        "cash flow", "operating activities", "investing activities",
        "financing activities", "capital expenditures", "free cash flow"
    ]
    
    for table in tables:
        if not table or len(table) < 2:
            continue
        
        text_sample = " ".join([
            " ".join([str(cell).lower() for cell in row if cell])
            for row in table[:5]
        ])
        
        matches = sum(1 for kw in keywords if kw in text_sample)
        
        if matches >= 3:
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
        period_label = _parse_period_label(cell, period_type)
        if period_label:
            period_columns.append({
                "index": idx,
                "period": period_label
            })
    
    if not period_columns:
        # Fallback: use column indices and try to infer from data
        period_columns = [{"index": i, "period": None} for i in range(1, len(header_row))]
    
    # Initialize period data structures
    periods = [{
        "period": col["period"],
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


def _parse_period_label(label: str, period_type: str) -> Optional[str]:
    """
    Parse period label from table header.
    
    Examples:
        "2024" -> "2024"
        "Q3 2024" -> "2024 Q3"
        "December 31, 2024" -> "2024"
        "Three Months Ended Sep 30, 2024" -> "2024 Q3"
    """
    if not label:
        return None
    
    label = label.strip()
    
    # Match year
    year_match = re.search(r'\b(20\d{2})\b', label)
    if not year_match:
        return None
    
    year = year_match.group(1)
    
    # Match quarter if quarterly
    if period_type == "Quarterly":
        quarter_patterns = [
            (r'\bq[1-4]\b', lambda m: f"Q{m.group(0)[1]}"),
            (r'\b(first|1st)\s+quarter\b', lambda m: "Q1"),
            (r'\b(second|2nd)\s+quarter\b', lambda m: "Q2"),
            (r'\b(third|3rd)\s+quarter\b', lambda m: "Q3"),
            (r'\b(fourth|4th)\s+quarter\b', lambda m: "Q4"),
            # Month-based detection
            (r'\b(january|february|march)\b', lambda m: "Q1"),
            (r'\b(april|may|june)\b', lambda m: "Q2"),
            (r'\b(july|august|september|sep)\b', lambda m: "Q3"),
            (r'\b(october|november|december|dec)\b', lambda m: "Q4"),
        ]
        
        for pattern, extractor in quarter_patterns:
            match = re.search(pattern, label.lower())
            if match:
                quarter = extractor(match)
                return f"{year} {quarter}"
        
        # Default to Q4 if quarter not specified for annual-looking label
        return f"{year} Q4"
    
    # Annual period
    return year


def _map_label_to_field(label: str, statement_type: str) -> Optional[str]:
    """Map row label to CF Financial Period field name."""
    label = label.lower()
    
    # Income statement mappings
    income_mappings = {
        "revenue": ["revenue", "total revenue", "net revenue", "sales", "net sales"],
        "cost_of_revenue": ["cost of revenue", "cost of sales", "cost of goods sold", "cogs"],
        "operating_expenses": ["operating expenses", "operating expense", "total operating expenses"],
        "operating_income": ["operating income", "income from operations", "operating profit"],
        "interest_expense": ["interest expense", "interest paid", "net interest expense"],
        "net_income": ["net income", "net earnings", "net profit", "earnings"],
        "ebitda": ["ebitda", "adjusted ebitda"],
        "depreciation_amortization": ["depreciation and amortization", "depreciation & amortization", "d&a"]
    }
    
    # Balance sheet mappings
    balance_mappings = {
        "total_assets": ["total assets", "assets"],
        "total_liabilities": ["total liabilities", "liabilities"],
        "stockholders_equity": ["stockholders equity", "shareholders equity", "total equity", "equity"],
        "total_debt": ["total debt", "long-term debt", "debt"],
        "cash_and_equivalents": ["cash and cash equivalents", "cash and equivalents", "cash"]
    }
    
    # Cash flow mappings
    cash_flow_mappings = {
        "operating_cash_flow": ["cash from operating activities", "operating cash flow", "cash flow from operations"],
        "capital_expenditures": ["capital expenditures", "capex", "capital expenditure", "purchases of property"],
        "free_cash_flow": ["free cash flow", "fcf"]
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
    
    # Remove currency symbols and commas
    value_str = re.sub(r'[$€£,\s]', '', value_str)
    
    # Check for magnitude suffixes
    multiplier = 1.0
    if value_str.endswith("B") or value_str.endswith("b"):
        multiplier = 1_000_000_000
        value_str = value_str[:-1]
    elif value_str.endswith("M") or value_str.endswith("m"):
        multiplier = 1_000_000
        value_str = value_str[:-1]
    elif value_str.endswith("K") or value_str.endswith("k"):
        multiplier = 1_000
        value_str = value_str[:-1]
    
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
        # Get full file path
        file_path = frappe.get_site_path() + file_url
        
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

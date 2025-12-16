import frappe

def create_and_extract_test_security(symbol: str = "AAPL"):
    """
    Create a CF Security test record if missing, fetch fundamentals,
    and trigger financial data extraction.
    """
    # Try to get existing
    name = symbol
    try:
        sec = frappe.get_doc("CF Security", name)
    except frappe.DoesNotExistError:
        sec = frappe.new_doc("CF Security")
        sec.security_name = symbol
        sec.symbol = symbol
        sec.security_type = "Stock"
        sec.insert()

    # Fetch data with fundamentals and trigger extraction
    sec.fetch_data(with_fundamentals=True)
    return {"name": sec.name, "message": "Fetch and extraction queued"}

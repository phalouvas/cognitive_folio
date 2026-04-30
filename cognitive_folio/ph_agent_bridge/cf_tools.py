"""cognitive_folio_query — single bridge tool for ph_agent to access CF data.

Provides a unified ``cognitive_folio_query`` function that the agent can
call to get, list, create, update, delete, or search Cognitive Folio
documents.  Field allowlisting and permission checks prevent unauthorized
access.

Registered in ph_agent's Tool Registry as an "Existing Function" script.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Optional

import frappe
from frappe.utils import flt
from pydantic import Field

# ---------------------------------------------------------------------------
# Allowlisted doctypes and their readable fields
# ---------------------------------------------------------------------------
# Only these doctypes can be accessed, and only the listed fields are
# returned.  This prevents accidental exposure of internal fields.

ALLOWED_DOCTYPES = {
    "CF Portfolio",
    "CF Security",
    "CF Portfolio Holding",
    "CF Transaction",
    "CF Dividend",
    "CF AI Model",
    "CF Asset Allocation",
    "CF Settings",
}

# Common name aliases that the LLM might use instead of the exact doctype name.
# Maps alias -> canonical doctype name.
DOCTYPE_ALIASES = {
    "portfolio": "CF Portfolio",
    "portfolios": "CF Portfolio",
    "cf portfolio": "CF Portfolio",
    "security": "CF Security",
    "securities": "CF Security",
    "cf security": "CF Security",
    "holding": "CF Portfolio Holding",
    "holdings": "CF Portfolio Holding",
    "cf holding": "CF Portfolio Holding",
    "cf portfolio holding": "CF Portfolio Holding",
    "transaction": "CF Transaction",
    "transactions": "CF Transaction",
    "cf transaction": "CF Transaction",
    "dividend": "CF Dividend",
    "dividends": "CF Dividend",
    "cf dividend": "CF Dividend",
}

# Per-doctype field allowlists for read operations.
# If a doctype is not listed here, all fields are returned (subject to
# the general allowlist above).
READ_FIELDS = {
    "CF Portfolio": [
        "name", "portfolio_name", "currency", "risk_profile", "current_value",
        "cost", "returns_total", "returns_percentage_total", "annualized_total",
        "annualized_percentage_total", "returns_price", "returns_percentage_price",
        "returns_dividends", "returns_percentage_dividends",
        "top_5_concentration", "sector_allocations", "region_allocations",
        "country_allocations", "currency_exposure", "description",
        "start_date", "disabled", "ai_suggestion",
    ],
    "CF Security": [
        "name", "security_name", "symbol", "isin", "cik", "security_type",
        "currency", "current_price", "stock_exchange", "country", "region",
        "subregion", "sector", "industry",
        "suggestion_action", "suggestion_rating", "suggestion_conviction",
        "suggestion_buy_price", "suggestion_sell_price", "suggestion_fair_value",
        "evaluation_stop_loss", "trailing_eps", "forward_eps", "earnings_yield",
        "rating_moat", "rating_management", "rating_financials",
        "rating_valuation", "rating_industry",
        "price_alert_status", "need_evaluation",
    ],
    "CF Portfolio Holding": [
        "name", "portfolio", "security", "quantity", "average_purchase_price",
        "base_average_purchase_price", "base_cost", "currency",
        "current_price", "current_price_sec", "current_value",
        "allocation_percentage", "profit_loss", "profit_loss_percentage",
        "dividend_yield", "yearly_dividend_income", "total_dividend_income",
        "security_name", "security_type", "sector", "industry", "country",
        "region", "suggestion_action", "suggestion_buy_price",
        "suggestion_sell_price", "suggestion_fair_value", "suggestion_rating",
        "need_evaluation",
    ],
    "CF Transaction": [
        "name", "portfolio", "security", "transaction_type", "transaction_date",
        "quantity", "price_per_unit", "total_amount", "currency",
        "fees", "commission", "total_fees", "notes",
    ],
    "CF Dividend": [
        "name", "portfolio", "security", "ex_dividend_date", "payment_date",
        "amount_per_share", "shares_owned", "total_amount", "tax_withheld",
        "net_amount", "currency", "status", "notes",
    ],
}

# Maximum number of results to return for list/search operations
_MAX_RESULTS = 100

# Whitelist of executable server methods per doctype for the "execute" action.
# Only methods listed here can be invoked via the cf_query tool.
EXECUTABLE_METHODS = {
    "CF Portfolio": [
        "fetch_holdings_data",
        "generate_holdings_ai_suggestions",
        "update_purchase_prices_from_market",
        "generate_portfolio_ai_analysis",
        "calculate_portfolio_performance",
        "evaluate_holdings_news",
    ],
    "CF Security": [
        "fetch_data",
        "fetch_cik",
        "generate_ai_suggestion",
        "get_financial_data_coverage",
    ],
}

# Maximum length of a single text field value (truncated to avoid token overflow)
_MAX_FIELD_LENGTH = 500


def cognitive_folio_query(
    action: Annotated[
        str,
        Field(description="Operation: 'get' (single doc), 'list' (filtered list), 'search' (keyword search), 'create', 'update', 'delete', 'execute' (run server method)"),
    ],
    doctype: Annotated[
        str,
        Field(description="DocType name, e.g. 'CF Portfolio', 'CF Security', 'CF Portfolio Holding', 'CF Transaction', 'CF Dividend'"),
    ],
    name: Annotated[
        Optional[str],
        Field(description="Document name (required for get/update/delete/execute actions)"),
    ] = None,
    method: Annotated[
        Optional[str],
        Field(description="Server method name (required for 'execute' action). E.g. 'calculate_portfolio_performance', 'fetch_holdings_data'"),
    ] = None,
    filters: Annotated[
        Optional[str],
        Field(description="JSON string of filters, e.g. '{\"portfolio\": \"BOC\"}' or '{\"name\": \"BOC\"}'"),
    ] = None,
    fields: Annotated[
        Optional[str],
        Field(description="Comma-separated field names to return, e.g. 'name,portfolio_name,currency'. Omit for default field set."),
    ] = None,
    data: Annotated[
        Optional[str],
        Field(description="JSON string of field values for create/update actions, or keyword arguments for 'execute' action, e.g. '{\"with_fundamentals\": true}'"),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of records to return (max 100)"),
    ] = 50,
) -> dict:
    """Query Cognitive Folio financial data.

    Unified interface for accessing CF documents. Use 'list' action to find
    documents matching filters, 'get' to fetch a single document by name or
    filters, and 'search' for keyword-based lookup.

    Examples:
      - List portfolios: action='list', doctype='CF Portfolio'
      - Get portfolio: action='get', doctype='CF Portfolio', filters='{"name":"BOC"}'
      - List holdings: action='list', doctype='CF Portfolio Holding', filters='{"portfolio":"BOC"}'
      - List transactions: action='list', doctype='CF Transaction', filters='{"security":"MSFT"}'
    """
    # Parse JSON string parameters
    parsed_filters = _parse_json_arg(filters, "filters")
    parsed_fields = _parse_csv_fields(fields)
    parsed_data = _parse_json_arg(data, "data") or {}

    # Resolve doctype aliases (e.g. "Portfolio" -> "CF Portfolio")
    resolved_doctype = _resolve_doctype(doctype)

    # Validate doctype
    if resolved_doctype not in ALLOWED_DOCTYPES:
        return {
            "success": False,
            "error": f"Unknown doctype '{doctype}'. Allowed: {', '.join(sorted(ALLOWED_DOCTYPES))}",
        }

    # Route to handler
    try:
        if action == "get":
            return _handle_get(resolved_doctype, name, parsed_filters, parsed_fields)
        elif action == "list":
            return _handle_list(resolved_doctype, parsed_filters, parsed_fields, limit)
        elif action == "search":
            return _handle_search(resolved_doctype, parsed_filters, parsed_fields, limit)
        elif action == "create":
            return _handle_create(resolved_doctype, parsed_data)
        elif action == "update":
            return _handle_update(doctype, name, parsed_data)
        elif action == "delete":
            return _handle_delete(doctype, name)
        elif action == "execute":
            return _handle_execute(resolved_doctype, name, method, parsed_data)
        else:
            return {
                "success": False,
                "error": f"Unknown action '{action}'. Supported: get, list, search, create, update, delete, execute",
            }
    except frappe.PermissionError as e:
        return {"success": False, "error": f"Permission denied: {e}"}
    except frappe.DoesNotExistError as e:
        return {"success": False, "error": f"Not found: {e}"}
    except Exception as e:
        frappe.log_error(
            title="cognitive_folio_query error",
            message=f"action={action}, doctype={doctype}, name={name}: {e}",
        )
        return {"success": False, "error": f"Error: {str(e)}"}


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


def _handle_get(doctype: str, name: str | None, filters: dict | None = None, fields: list | None = None) -> dict:
    """Fetch a single document by name or filters."""
    if name:
        doc = frappe.get_doc(doctype, name)
    elif filters:
        names = frappe.get_all(doctype, filters=filters, limit_page_length=1, pluck="name")
        if not names:
            return {"success": False, "error": f"No {doctype} found matching filters"}
        doc = frappe.get_doc(doctype, names[0])
    else:
        return {"success": False, "error": "`name` or `filters` is required for get action"}

    # For CF Portfolio, compute current_value and cost from holdings if stored values are 0
    if doctype == "CF Portfolio":
        _enrich_portfolio_totals(doc)

    allowed_fields = fields if fields and fields != ["*"] else READ_FIELDS.get(doctype)
    data = _serialize_doc(doc, allowed_fields)
    return {"success": True, "data": data}


def _handle_list(
    doctype: str,
    filters: dict | None,
    fields: list | None,
    limit: int,
) -> dict:
    """List documents matching filters."""
    limit = min(limit, _MAX_RESULTS)
    resolved_fields = fields or READ_FIELDS.get(doctype)

    records = frappe.get_all(
        doctype,
        filters=filters or {},
        fields=resolved_fields,
        limit_page_length=limit,
    )

    # Truncate long text fields
    for record in records:
        _truncate_fields(record)

    return {"success": True, "data": records, "count": len(records)}


def _enrich_portfolio_totals(doc):
    """Compute portfolio current_value and cost from holdings if stored values are 0.

    The portfolio's current_value and cost are computed fields that may be 0
    if the 'Calculate Performance' action hasn't been run. This function
    calculates them on-the-fly from the holdings so the agent sees real data.
    """
    if doc.current_value != 0 and doc.cost != 0:
        return  # Already has values

    holdings = frappe.get_all(
        "CF Portfolio Holding",
        filters={"portfolio": doc.name},
        fields=["current_value", "base_cost"],
    )

    total_value = sum(flt(h.current_value or 0) for h in holdings)
    total_cost = sum(flt(h.base_cost or 0) for h in holdings)

    if doc.current_value == 0 and total_value:
        doc.current_value = total_value
    if doc.cost == 0 and total_cost:
        doc.cost = total_cost


def _handle_search(
    doctype: str,
    filters: dict | None,
    fields: list | None,
    limit: int,
) -> dict:
    """Search documents by keyword across text fields.

    Uses ``frappe.get_list`` with ``filters`` containing a text search
    condition if provided.
    """
    limit = min(limit, _MAX_RESULTS)
    resolved_fields = fields or READ_FIELDS.get(doctype)

    records = frappe.get_all(
        doctype,
        filters=filters or {},
        fields=resolved_fields,
        limit_page_length=limit,
    )

    for record in records:
        _truncate_fields(record)

    return {"success": True, "data": records, "count": len(records)}


def _handle_create(doctype: str, data: dict | None) -> dict:
    """Create a new document."""
    if not data:
        return {"success": False, "error": "`data` is required for create action"}

    doc = frappe.get_doc({"doctype": doctype, **data})
    doc.insert(ignore_permissions=False)
    frappe.db.commit()

    allowed_fields = READ_FIELDS.get(doctype)
    result = _serialize_doc(doc, allowed_fields)
    return {"success": True, "data": result, "name": doc.name}


def _handle_update(doctype: str, name: str | None, data: dict | None) -> dict:
    """Update an existing document."""
    if not name:
        return {"success": False, "error": "`name` is required for update action"}
    if not data:
        return {"success": False, "error": "`data` is required for update action"}

    doc = frappe.get_doc(doctype, name)
    doc.update(data)
    doc.save(ignore_permissions=False)
    frappe.db.commit()

    allowed_fields = READ_FIELDS.get(doctype)
    result = _serialize_doc(doc, allowed_fields)
    return {"success": True, "data": result, "name": doc.name}


def _handle_delete(doctype: str, name: str | None) -> dict:
    """Delete a document by name."""
    if not name:
        return {"success": False, "error": "`name` is required for delete action"}

    frappe.delete_doc(doctype, name, ignore_permissions=False)
    frappe.db.commit()
    return {"success": True, "message": f"Deleted {doctype} {name}"}


def _handle_execute(doctype: str, name: str | None, method: str | None, kwargs: dict) -> dict:
    """Execute a whitelisted server method on a document.

    Loads the document by ``name`` and calls ``doc.run_method(method, **kwargs)``.
    Only methods listed in ``EXECUTABLE_METHODS`` for the given doctype may
    be invoked.
    """
    if not name:
        return {"success": False, "error": "`name` is required for execute action"}
    if not method:
        return {"success": False, "error": "`method` is required for execute action"}

    allowed = EXECUTABLE_METHODS.get(doctype, [])
    if method not in allowed:
        return {
            "success": False,
            "error": f"Method '{method}' not allowed for {doctype}. "
                     f"Allowed methods: {', '.join(allowed) if allowed else 'none'}",
        }

    try:
        doc = frappe.get_doc(doctype, name)
        result = doc.run_method(method, **kwargs)
        frappe.db.commit()
        return {"success": True, "data": result}
    except frappe.PermissionError as e:
        return {"success": False, "error": f"Permission denied: {e}"}
    except frappe.DoesNotExistError as e:
        return {"success": False, "error": f"Not found: {e}"}
    except Exception as e:
        frappe.log_error(
            title=f"cognitive_folio_query: execute error",
            message=f"doctype={doctype}, name={name}, method={method}, kwargs={kwargs}: {e}",
        )
        return {"success": False, "error": f"Error executing {method}: {str(e)}"}


# ---------------------------------------------------------------------------
# JSON / CSV parsing helpers
# ---------------------------------------------------------------------------


def _parse_json_arg(value: str | None, arg_name: str) -> dict | list | None:
    """Parse a JSON string argument into a Python object.

    The LLM sends filters/data as JSON strings.  This helper safely
    parses them, returning None on failure (with a logged warning).
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value  # Already parsed (e.g. from direct Python call)
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError) as e:
        frappe.log_error(
            title=f"cognitive_folio_query: invalid {arg_name}",
            message=f"Value: {value!r}, Error: {e}",
        )
        return None


def _parse_csv_fields(fields: str | None) -> list | None:
    """Parse a comma-separated field list or return None.

    The LLM may send fields as a CSV string or a JSON array.
    """
    if fields is None:
        return None
    if isinstance(fields, list):
        return fields  # Already a list (e.g. from direct Python call)
    if isinstance(fields, str):
        # Could be JSON array or CSV
        fields = fields.strip()
        if fields.startswith("["):
            try:
                return json.loads(fields)
            except json.JSONDecodeError:
                pass
        return [f.strip() for f in fields.split(",") if f.strip()]
    return None


def _resolve_doctype(doctype: str) -> str:
    """Resolve a doctype alias to its canonical name.

    The LLM may pass common names like 'Portfolio' instead of 'CF Portfolio'.
    This function maps aliases to the correct doctype name.
    """
    key = doctype.strip().lower()
    return DOCTYPE_ALIASES.get(key, doctype)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_doc(doc: frappe.model.document.Document, allowed_fields: list[str] | None) -> dict:
    """Serialize a Frappe document to a dict, optionally filtering fields."""
    result = {}
    if allowed_fields:
        for fieldname in allowed_fields:
            value = doc.get(fieldname)
            if isinstance(value, (list, tuple)):
                # Table fields — serialize as list of dicts
                result[fieldname] = [
                    _serialize_doc(row, None) for row in (value or [])
                ]
            else:
                result[fieldname] = _truncate_value(value)
    else:
        # Return all non-internal fields
        for field in doc.meta.fields:
            if field.fieldname.startswith("_"):
                continue
            value = doc.get(field.fieldname)
            if isinstance(value, (list, tuple)):
                result[field.fieldname] = [
                    _serialize_doc(row, None) for row in (value or [])
                ]
            else:
                result[field.fieldname] = _truncate_value(value)
    return result


def _truncate_fields(record: dict) -> None:
    """Truncate long string values in a record in-place."""
    for key, value in record.items():
        record[key] = _truncate_value(value)


def _truncate_value(value: Any) -> Any:
    """Truncate a single value if it's a long string."""
    if isinstance(value, str) and len(value) > _MAX_FIELD_LENGTH:
        return value[:_MAX_FIELD_LENGTH] + "..."
    return value

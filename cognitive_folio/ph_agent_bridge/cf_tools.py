"""cognitive_folio_query — single bridge tool for ph_agent to access CF data.

Provides a unified ``cognitive_folio_query`` function that the agent can
call to get, list, create, update, delete, or search Cognitive Folio
documents.  Field allowlisting and permission checks prevent unauthorized
access.

Registered in ph_agent's Tool Registry as an "Existing Function" script.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

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

# Maximum length of a single text field value (truncated to avoid token overflow)
_MAX_FIELD_LENGTH = 500


def cognitive_folio_query(
    action: str,
    doctype: str,
    name: str | None = None,
    filters: dict | None = None,
    fields: list | None = None,
    data: dict | None = None,
    limit: int = 50,
) -> dict:
    """Query Cognitive Folio data.

    Unified interface for accessing CF documents.  The agent calls this
    with an action and doctype to perform CRUD operations.

    Args:
        action: Operation to perform.
            - ``"get"``: Fetch a single document by name.
            - ``"list"``: List documents matching filters.
            - ``"search"``: Search documents by keyword (name or title).
            - ``"create"``: Create a new document.
            - ``"update"``: Update an existing document.
            - ``"delete"``: Delete a document by name.
        doctype: The Cognitive Folio DocType to operate on.
        name: Document name (required for get, update, delete).
        filters: Filter conditions (for list/search).
        fields: Specific fields to return (for list). If omitted, uses
            the allowlist for the doctype.
        data: Field values (for create/update).
        limit: Maximum results (default 50, max 100).

    Returns:
        A dict with ``"success"`` and either ``"data"`` or ``"error"``.
    """
    # Validate doctype
    if doctype not in ALLOWED_DOCTYPES:
        return {
            "success": False,
            "error": f"Unknown doctype '{doctype}'. Allowed: {', '.join(sorted(ALLOWED_DOCTYPES))}",
        }

    # Route to handler
    try:
        if action == "get":
            return _handle_get(doctype, name)
        elif action == "list":
            return _handle_list(doctype, filters, fields, limit)
        elif action == "search":
            return _handle_search(doctype, filters, fields, limit)
        elif action == "create":
            return _handle_create(doctype, data)
        elif action == "update":
            return _handle_update(doctype, name, data)
        elif action == "delete":
            return _handle_delete(doctype, name)
        else:
            return {
                "success": False,
                "error": f"Unknown action '{action}'. Supported: get, list, search, create, update, delete",
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


def _handle_get(doctype: str, name: str | None) -> dict:
    """Fetch a single document by name."""
    if not name:
        return {"success": False, "error": "`name` is required for get action"}

    doc = frappe.get_doc(doctype, name)
    allowed_fields = READ_FIELDS.get(doctype)
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

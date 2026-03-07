import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Date", "fieldname": "log_date", "fieldtype": "Date", "width": 110},
        {"label": "Query Type", "fieldname": "query_type", "fieldtype": "Data", "width": 120},
        {"label": "Providers", "fieldname": "providers", "fieldtype": "Data", "width": 220},
        {"label": "Result Count", "fieldname": "result_count", "fieldtype": "Int", "width": 110},
        {"label": "Violation Count", "fieldname": "violation_count", "fieldtype": "Int", "width": 120},
        {"label": "User", "fieldname": "user", "fieldtype": "Data", "width": 150},
    ]

    conditions = []
    values = {}

    from_date = filters.get("from_date")
    if from_date:
        conditions.append("log_date >= %(from_date)s")
        values["from_date"] = from_date

    to_date = filters.get("to_date")
    if to_date:
        conditions.append("log_date <= %(to_date)s")
        values["to_date"] = to_date

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    data = frappe.db.sql(
        f"""
        SELECT
            log_date,
            query_type,
            providers,
            result_count,
            violation_count,
            user
        FROM `tabCF Search Compliance Log`
        {where_clause}
        ORDER BY log_date DESC, creation DESC
        """,
        values,
        as_dict=True,
    )

    return columns, data

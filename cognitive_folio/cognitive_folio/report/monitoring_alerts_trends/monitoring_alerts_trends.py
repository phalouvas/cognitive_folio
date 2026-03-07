import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Date", "fieldname": "alert_date", "fieldtype": "Date", "width": 110},
        {"label": "Alert Type", "fieldname": "alert_type", "fieldtype": "Data", "width": 130},
        {"label": "Severity", "fieldname": "severity", "fieldtype": "Data", "width": 90},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": "Model", "fieldname": "model", "fieldtype": "Data", "width": 140},
        {"label": "Message", "fieldname": "message", "fieldtype": "Data", "width": 320},
    ]

    conditions = []
    values = {}

    from_date = filters.get("from_date")
    if from_date:
        conditions.append("alert_date >= %(from_date)s")
        values["from_date"] = from_date

    to_date = filters.get("to_date")
    if to_date:
        conditions.append("alert_date <= %(to_date)s")
        values["to_date"] = to_date

    status = (filters.get("status") or "").strip()
    if status:
        conditions.append("status = %(status)s")
        values["status"] = status

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    data = frappe.db.sql(
        f"""
        SELECT
            alert_date,
            alert_type,
            severity,
            status,
            model,
            message
        FROM `tabCF Monitoring Alert`
        {where_clause}
        ORDER BY alert_date DESC, creation DESC
        """,
        values,
        as_dict=True,
    )

    return columns, data

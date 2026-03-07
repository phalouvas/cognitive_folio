import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Date", "fieldname": "metric_date", "fieldtype": "Date", "width": 110},
        {"label": "Tool", "fieldname": "tool_name", "fieldtype": "Data", "width": 180},
        {"label": "Calls", "fieldname": "calls", "fieldtype": "Int", "width": 90},
        {"label": "Success", "fieldname": "success_count", "fieldtype": "Int", "width": 90},
        {"label": "Failure", "fieldname": "failure_count", "fieldtype": "Int", "width": 90},
        {"label": "Retries", "fieldname": "retry_count", "fieldtype": "Int", "width": 90},
        {"label": "Success Rate", "fieldname": "success_rate", "fieldtype": "Percent", "width": 120},
        {"label": "Avg Duration (ms)", "fieldname": "avg_duration_ms", "fieldtype": "Float", "width": 130},
        {"label": "Last Model", "fieldname": "last_model", "fieldtype": "Data", "width": 140},
        {"label": "Last Intent", "fieldname": "last_intent", "fieldtype": "Data", "width": 140},
    ]

    conditions = []
    values = {}

    from_date = filters.get("from_date")
    if from_date:
        conditions.append("ctm.metric_date >= %(from_date)s")
        values["from_date"] = from_date

    to_date = filters.get("to_date")
    if to_date:
        conditions.append("ctm.metric_date <= %(to_date)s")
        values["to_date"] = to_date

    tool_name = (filters.get("tool_name") or "").strip()
    if tool_name:
        conditions.append("LOWER(ctm.tool_name) LIKE %(tool_name_like)s")
        values["tool_name_like"] = f"%{tool_name.lower()}%"

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    data = frappe.db.sql(
        f"""
        SELECT
          ctm.metric_date,
          ctm.tool_name,
          ctm.calls,
          ctm.success_count,
          ctm.failure_count,
          ctm.retry_count,
          ctm.success_rate,
          ctm.avg_duration_ms,
          ctm.last_model,
          ctm.last_intent
        FROM `tabCF Tool Metric` ctm
        {where_clause}
        ORDER BY ctm.metric_date DESC, ctm.calls DESC, ctm.tool_name ASC
        """,
        values,
        as_dict=True,
    )

    return columns, data

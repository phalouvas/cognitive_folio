import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Date", "fieldname": "metric_date", "fieldtype": "Date", "width": 110},
        {"label": "Runs", "fieldname": "runs", "fieldtype": "Int", "width": 90},
        {"label": "Success", "fieldname": "success_runs", "fieldtype": "Int", "width": 90},
        {"label": "Failed", "fieldname": "failed_runs", "fieldtype": "Int", "width": 90},
        {"label": "Chats Scanned", "fieldname": "chats_scanned", "fieldtype": "Int", "width": 120},
        {"label": "Rows Deleted", "fieldname": "rows_deleted", "fieldtype": "Int", "width": 120},
        {"label": "Last Status", "fieldname": "last_status", "fieldtype": "Data", "width": 120},
        {"label": "Last Reason", "fieldname": "last_reason", "fieldtype": "Data", "width": 180},
        {"label": "Last Run", "fieldname": "last_run_at", "fieldtype": "Datetime", "width": 160},
    ]

    conditions = []
    values = {}

    from_date = filters.get("from_date")
    if from_date:
        conditions.append("mcm.metric_date >= %(from_date)s")
        values["from_date"] = from_date

    to_date = filters.get("to_date")
    if to_date:
        conditions.append("mcm.metric_date <= %(to_date)s")
        values["to_date"] = to_date

    status = (filters.get("status") or "").strip().lower()
    if status in {"success", "failed"}:
        conditions.append("LOWER(mcm.last_status) = %(status)s")
        values["status"] = status

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    data = frappe.db.sql(
        f"""
        SELECT
          mcm.metric_date,
          mcm.runs,
          mcm.success_runs,
          mcm.failed_runs,
          mcm.chats_scanned,
          mcm.rows_deleted,
          mcm.last_status,
          mcm.last_reason,
          mcm.last_run_at
        FROM `tabCF Memory Cleanup Metric` mcm
        {where_clause}
        ORDER BY mcm.metric_date DESC
        """,
        values,
        as_dict=True,
    )

    return columns, data

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Date", "fieldname": "metric_date", "fieldtype": "Date", "width": 110},
        {"label": "Experiment", "fieldname": "experiment", "fieldtype": "Link", "options": "CF Experiment", "width": 170},
        {"label": "Variant", "fieldname": "variant", "fieldtype": "Data", "width": 120},
        {"label": "Quality", "fieldname": "quality_score", "fieldtype": "Float", "width": 100},
        {"label": "Estimated Cost", "fieldname": "estimated_cost_usd", "fieldtype": "Currency", "width": 120},
        {"label": "Response Time (ms)", "fieldname": "response_time_ms", "fieldtype": "Float", "width": 130},
    ]

    conditions = []
    values = {}

    from_date = filters.get("from_date")
    if from_date:
        conditions.append("metric_date >= %(from_date)s")
        values["from_date"] = from_date

    to_date = filters.get("to_date")
    if to_date:
        conditions.append("metric_date <= %(to_date)s")
        values["to_date"] = to_date

    experiment = filters.get("experiment")
    if experiment:
        conditions.append("experiment = %(experiment)s")
        values["experiment"] = experiment

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    data = frappe.db.sql(
        f"""
        SELECT
            metric_date,
            experiment,
            variant,
            quality_score,
            estimated_cost_usd,
            response_time_ms
        FROM `tabCF Experiment Metric`
        {where_clause}
        ORDER BY metric_date DESC, creation DESC
        """,
        values,
        as_dict=True,
    )

    return columns, data

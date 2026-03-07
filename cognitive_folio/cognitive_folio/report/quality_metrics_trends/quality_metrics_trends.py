import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Date", "fieldname": "metric_date", "fieldtype": "Date", "width": 110},
        {"label": "Model", "fieldname": "model", "fieldtype": "Data", "width": 170},
        {"label": "Messages", "fieldname": "messages", "fieldtype": "Int", "width": 90},
        {"label": "Quality", "fieldname": "quality_score", "fieldtype": "Float", "width": 90},
        {"label": "Relevance", "fieldname": "relevance_score", "fieldtype": "Float", "width": 90},
        {"label": "Completeness", "fieldname": "completeness_score", "fieldtype": "Float", "width": 110},
        {"label": "Grounding", "fieldname": "grounding_score", "fieldtype": "Float", "width": 90},
        {"label": "Estimated Cost", "fieldname": "estimated_cost_usd", "fieldtype": "Currency", "width": 120},
        {"label": "User Feedback", "fieldname": "user_feedback_avg", "fieldtype": "Float", "width": 110},
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

    model = (filters.get("model") or "").strip()
    if model:
        conditions.append("LOWER(model) LIKE %(model)s")
        values["model"] = f"%{model.lower()}%"

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    data = frappe.db.sql(
        f"""
        SELECT
            metric_date,
            model,
            messages,
            quality_score,
            relevance_score,
            completeness_score,
            grounding_score,
            estimated_cost_usd,
            user_feedback_avg
        FROM `tabCF Quality Metric`
        {where_clause}
        ORDER BY metric_date DESC, model ASC
        """,
        values,
        as_dict=True,
    )

    return columns, data

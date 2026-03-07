import frappe


class ToolMetricsStore:
    """Persist per-tool effectiveness metrics as daily rollups."""

    DOCTYPE_NAME = "CF Tool Metric"

    def persist_daily_rollups(self, metrics, context=None):
        context = context or {}
        if not isinstance(metrics, dict) or not metrics:
            return {"persisted": False, "reason": "no_metrics"}

        if not frappe.db.exists("DocType", self.DOCTYPE_NAME):
            return {"persisted": False, "reason": "doctype_missing"}

        metric_date = context.get("metric_date") or frappe.utils.nowdate()
        persisted_count = 0

        for tool_name, item in metrics.items():
            if not isinstance(item, dict):
                continue

            calls = max(0, int(item.get("calls", 0) or 0))
            success = max(0, int(item.get("success", 0) or 0))
            failure = max(0, int(item.get("failure", 0) or 0))
            retries = max(0, int(item.get("retries", 0) or 0))
            avg_duration_ms = float(item.get("avg_duration_ms", 0.0) or 0.0)

            if calls <= 0:
                continue

            existing_name = frappe.db.get_value(
                self.DOCTYPE_NAME,
                {"metric_date": metric_date, "tool_name": tool_name},
                "name",
            )

            try:
                if existing_name:
                    doc = frappe.get_doc(self.DOCTYPE_NAME, existing_name)
                    previous_calls = int(doc.calls or 0)
                    previous_total_duration = float(doc.avg_duration_ms or 0.0) * previous_calls

                    total_calls = previous_calls + calls
                    doc.calls = total_calls
                    doc.success_count = int(doc.success_count or 0) + success
                    doc.failure_count = int(doc.failure_count or 0) + failure
                    doc.retry_count = int(doc.retry_count or 0) + retries
                    doc.avg_duration_ms = round((previous_total_duration + (avg_duration_ms * calls)) / max(1, total_calls), 2)
                    doc.success_rate = round(float(doc.success_count) / max(1, total_calls), 4)
                    doc.last_model = context.get("model")
                    doc.last_intent = context.get("intent")
                    doc.last_chat = context.get("chat")
                    doc.last_message = context.get("message")
                    doc.save(ignore_permissions=True)
                else:
                    success_rate = round(float(success) / max(1, calls), 4)
                    doc = frappe.get_doc(
                        {
                            "doctype": self.DOCTYPE_NAME,
                            "metric_date": metric_date,
                            "tool_name": tool_name,
                            "calls": calls,
                            "success_count": success,
                            "failure_count": failure,
                            "retry_count": retries,
                            "avg_duration_ms": round(avg_duration_ms, 2),
                            "success_rate": success_rate,
                            "last_model": context.get("model"),
                            "last_intent": context.get("intent"),
                            "last_chat": context.get("chat"),
                            "last_message": context.get("message"),
                        }
                    )
                    doc.insert(ignore_permissions=True)

                persisted_count += 1
            except Exception:
                frappe.log_error(title="ToolMetricsStore persist error", message=frappe.get_traceback())

        return {
            "persisted": persisted_count > 0,
            "persisted_count": persisted_count,
            "metric_date": metric_date,
        }

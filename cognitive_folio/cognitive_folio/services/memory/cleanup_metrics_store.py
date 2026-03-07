import frappe


class CleanupMetricsStore:
    """Persist daily cleanup execution metrics for vector-memory retention jobs."""

    DOCTYPE_NAME = "CF Memory Cleanup Metric"

    def persist_daily(self, cleanup_result, context=None):
        context = context or {}
        result = cleanup_result or {}

        if not frappe.db.exists("DocType", self.DOCTYPE_NAME):
            return {"persisted": False, "reason": "doctype_missing"}

        metric_date = context.get("metric_date") or frappe.utils.nowdate()
        now_dt = context.get("run_at") or frappe.utils.now_datetime()

        pruned = bool(result.get("pruned", False))
        deleted = max(0, int(result.get("deleted", 0) or 0))
        chats = max(0, int(result.get("chats", 0) or 0))
        reason = str(result.get("reason") or "")[:140]
        status = "success" if pruned else "failed"

        existing_name = frappe.db.get_value(self.DOCTYPE_NAME, {"metric_date": metric_date}, "name")

        try:
            if existing_name:
                doc = frappe.get_doc(self.DOCTYPE_NAME, existing_name)
                doc.runs = int(doc.runs or 0) + 1
                doc.success_runs = int(doc.success_runs or 0) + (1 if pruned else 0)
                doc.failed_runs = int(doc.failed_runs or 0) + (0 if pruned else 1)
                doc.chats_scanned = int(doc.chats_scanned or 0) + chats
                doc.rows_deleted = int(doc.rows_deleted or 0) + deleted
                doc.last_status = status
                doc.last_reason = reason
                doc.last_run_at = now_dt
                doc.save(ignore_permissions=True)
            else:
                doc = frappe.get_doc(
                    {
                        "doctype": self.DOCTYPE_NAME,
                        "metric_date": metric_date,
                        "runs": 1,
                        "success_runs": 1 if pruned else 0,
                        "failed_runs": 0 if pruned else 1,
                        "chats_scanned": chats,
                        "rows_deleted": deleted,
                        "last_status": status,
                        "last_reason": reason,
                        "last_run_at": now_dt,
                    }
                )
                doc.insert(ignore_permissions=True)

            return {"persisted": True, "metric_date": metric_date, "status": status}
        except Exception:
            try:
                frappe.log_error(title="CleanupMetricsStore persist error", message=frappe.get_traceback())
            except Exception:
                pass
            return {"persisted": False, "reason": "persist_failed"}

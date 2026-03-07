# pyright: reportMissingImports=false
import hashlib
import math

import frappe


class AnswerQualityScorer:
    def score(self, prompt, response, tool_trace=None):
        prompt_text = str(prompt or "").strip()
        response_text = str(response or "").strip()
        trace = tool_trace or []

        relevance = min(1.0, len(set(prompt_text.lower().split()).intersection(set(response_text.lower().split()))) / max(1, len(set(prompt_text.lower().split()))))
        completeness = min(1.0, len(response_text) / 900.0)
        grounding = min(1.0, (sum(1 for t in trace if (t or {}).get("ok")) / max(1, len(trace))) if trace else 0.7)

        total = round((0.45 * relevance) + (0.35 * completeness) + (0.20 * grounding), 4)
        return {
            "quality_score": total,
            "relevance_score": round(relevance, 4),
            "completeness_score": round(completeness, 4),
            "grounding_score": round(grounding, 4),
        }


class CostOptimizer:
    # Conservative placeholder unit prices; configurable later through feature flags.
    PROMPT_TOKEN_COST = 0.0000006
    COMPLETION_TOKEN_COST = 0.0000018
    TOOL_CALL_COST = 0.0002

    def estimate(self, usage, tool_trace=None):
        usage = usage or {}
        trace = tool_trace or []
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        tool_calls = len(trace)

        estimated_cost = (
            (prompt_tokens * self.PROMPT_TOKEN_COST)
            + (completion_tokens * self.COMPLETION_TOKEN_COST)
            + (tool_calls * self.TOOL_CALL_COST)
        )

        recommendation = "balanced"
        if tool_calls > 6 and estimated_cost > 0.01:
            recommendation = "reduce_tool_rounds"
        elif prompt_tokens > 100000:
            recommendation = "increase_summarization"

        return {
            "estimated_cost_usd": round(estimated_cost, 6),
            "tool_calls": tool_calls,
            "recommendation": recommendation,
        }


class MetricsCollector:
    DOCTYPE_NAME = "CF Quality Metric"

    def persist_quality_metric(self, metric):
        if not frappe.db.exists("DocType", self.DOCTYPE_NAME):
            return {"persisted": False, "reason": "doctype_missing"}

        metric_date = metric.get("metric_date") or frappe.utils.nowdate()
        model = str(metric.get("model") or "unknown")[:120]
        existing_name = frappe.db.get_value(self.DOCTYPE_NAME, {"metric_date": metric_date, "model": model}, "name")

        quality = float(metric.get("quality_score", 0.0) or 0.0)
        relevance = float(metric.get("relevance_score", 0.0) or 0.0)
        completeness = float(metric.get("completeness_score", 0.0) or 0.0)
        grounding = float(metric.get("grounding_score", 0.0) or 0.0)
        est_cost = float(metric.get("estimated_cost_usd", 0.0) or 0.0)
        prompt_tokens = int(metric.get("prompt_tokens", 0) or 0)
        completion_tokens = int(metric.get("completion_tokens", 0) or 0)
        messages = int(metric.get("messages", 1) or 1)
        user_feedback_avg = float(metric.get("user_feedback_avg", 0.0) or 0.0)

        try:
            if existing_name:
                doc = frappe.get_doc(self.DOCTYPE_NAME, existing_name)
                prev_messages = int(doc.messages or 0)
                total_messages = prev_messages + messages

                def weighted(prev_avg, new_val):
                    return ((float(prev_avg or 0.0) * prev_messages) + (float(new_val) * messages)) / max(1, total_messages)

                doc.messages = total_messages
                doc.quality_score = round(weighted(doc.quality_score, quality), 4)
                doc.relevance_score = round(weighted(doc.relevance_score, relevance), 4)
                doc.completeness_score = round(weighted(doc.completeness_score, completeness), 4)
                doc.grounding_score = round(weighted(doc.grounding_score, grounding), 4)
                doc.estimated_cost_usd = round(float(doc.estimated_cost_usd or 0.0) + est_cost, 6)
                doc.prompt_tokens = int(doc.prompt_tokens or 0) + prompt_tokens
                doc.completion_tokens = int(doc.completion_tokens or 0) + completion_tokens
                doc.user_feedback_avg = round(weighted(doc.user_feedback_avg, user_feedback_avg), 4)
                doc.last_chat = metric.get("chat")
                doc.last_message = metric.get("message")
                doc.save(ignore_permissions=True)
            else:
                doc = frappe.get_doc(
                    {
                        "doctype": self.DOCTYPE_NAME,
                        "metric_date": metric_date,
                        "model": model,
                        "messages": messages,
                        "quality_score": round(quality, 4),
                        "relevance_score": round(relevance, 4),
                        "completeness_score": round(completeness, 4),
                        "grounding_score": round(grounding, 4),
                        "estimated_cost_usd": round(est_cost, 6),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "user_feedback_avg": round(user_feedback_avg, 4),
                        "last_chat": metric.get("chat"),
                        "last_message": metric.get("message"),
                    }
                )
                doc.insert(ignore_permissions=True)
            return {"persisted": True}
        except Exception:
            frappe.log_error(title="MetricsCollector persist_quality_metric error", message=frappe.get_traceback())
            return {"persisted": False, "reason": "insert_failed"}

    def persist_experiment_metric(self, metric):
        if not frappe.db.exists("DocType", "CF Experiment Metric"):
            return {"persisted": False, "reason": "doctype_missing"}

        try:
            doc = frappe.get_doc(
                {
                    "doctype": "CF Experiment Metric",
                    "metric_date": metric.get("metric_date") or frappe.utils.nowdate(),
                    "experiment": metric.get("experiment"),
                    "variant": metric.get("variant"),
                    "quality_score": float(metric.get("quality_score", 0.0) or 0.0),
                    "estimated_cost_usd": float(metric.get("estimated_cost_usd", 0.0) or 0.0),
                    "response_time_ms": float(metric.get("response_time_ms", 0.0) or 0.0),
                    "chat": metric.get("chat"),
                    "chat_message": metric.get("chat_message"),
                }
            )
            doc.insert(ignore_permissions=True)
            return {"persisted": True, "name": doc.name}
        except Exception:
            frappe.log_error(title="MetricsCollector persist_experiment_metric error", message=frappe.get_traceback())
            return {"persisted": False, "reason": "insert_failed"}


class ExperimentManager:
    def assign_variant(self, chat_name):
        active = frappe.get_all(
            "CF Experiment",
            filters={"status": "Active"},
            fields=["name", "variants_json", "rollout_percentage"],
            order_by="modified desc",
            limit_page_length=1,
        )
        if not active:
            return {"experiment": None, "variant": "control"}

        exp = active[0]
        rollout_percentage = max(0.0, min(100.0, float(exp.get("rollout_percentage", 0.0) or 0.0)))
        bucket = int(hashlib.sha256(str(chat_name or "").encode("utf-8")).hexdigest()[:8], 16) % 100
        if bucket >= int(rollout_percentage):
            return {"experiment": exp.get("name"), "variant": "control"}

        variants = []
        try:
            variants = frappe.parse_json(exp.get("variants_json") or "[]")
        except Exception:
            variants = []
        variants = [str(v).strip() for v in variants if str(v).strip()]
        if not variants:
            variants = ["variant_a"]
        selected = variants[bucket % len(variants)]
        return {"experiment": exp.get("name"), "variant": selected}


class StatisticalAnalyzer:
    def compare_variants(self, metrics):
        grouped = {}
        for row in metrics or []:
            key = (row.get("experiment"), row.get("variant"))
            grouped.setdefault(key, []).append(float(row.get("quality_score", 0.0) or 0.0))

        summary = []
        for (experiment, variant), values in grouped.items():
            avg = sum(values) / max(1, len(values))
            variance = sum((v - avg) ** 2 for v in values) / max(1, len(values))
            summary.append(
                {
                    "experiment": experiment,
                    "variant": variant,
                    "samples": len(values),
                    "mean_quality": round(avg, 4),
                    "std_dev": round(math.sqrt(max(0.0, variance)), 4),
                }
            )

        return summary


class RolloutController:
    def determine_winner(self, summary_rows):
        by_exp = {}
        for row in summary_rows or []:
            by_exp.setdefault(row.get("experiment"), []).append(row)

        decisions = []
        for experiment, rows in by_exp.items():
            eligible = [r for r in rows if int(r.get("samples", 0) or 0) >= 5]
            if not eligible:
                continue
            winner = sorted(eligible, key=lambda x: (x.get("mean_quality", 0.0), x.get("samples", 0)), reverse=True)[0]
            decisions.append(
                {
                    "experiment": experiment,
                    "winner_variant": winner.get("variant"),
                    "mean_quality": winner.get("mean_quality"),
                    "samples": winner.get("samples"),
                }
            )
        return decisions


class AlertingSystem:
    DOCTYPE_NAME = "CF Monitoring Alert"

    def evaluate_and_create(self, quality_metric, config=None):
        config = config or {}
        if not frappe.db.exists("DocType", self.DOCTYPE_NAME):
            return {"created": False, "reason": "doctype_missing"}

        alerts = []
        quality_threshold = float(config.get("quality_alert_threshold", 0.45) or 0.45)
        cost_threshold = float(config.get("cost_alert_threshold", 0.015) or 0.015)

        if float(quality_metric.get("quality_score", 1.0) or 1.0) < quality_threshold:
            alerts.append(("quality_drop", f"Quality score below threshold: {quality_metric.get('quality_score')}"))

        if float(quality_metric.get("estimated_cost_usd", 0.0) or 0.0) > cost_threshold:
            alerts.append(("cost_spike", f"Estimated cost above threshold: {quality_metric.get('estimated_cost_usd')}"))

        created = 0
        for code, message in alerts:
            try:
                doc = frappe.get_doc(
                    {
                        "doctype": self.DOCTYPE_NAME,
                        "alert_date": frappe.utils.nowdate(),
                        "alert_type": code,
                        "severity": "High" if code == "quality_drop" else "Medium",
                        "message": message,
                        "status": "Open",
                        "model": quality_metric.get("model"),
                        "chat": quality_metric.get("chat"),
                        "chat_message": quality_metric.get("message"),
                    }
                )
                doc.insert(ignore_permissions=True)
                created += 1
            except Exception:
                frappe.log_error(title="AlertingSystem create alert error", message=frappe.get_traceback())

        return {"created": created > 0, "count": created}


class RealTimeMetrics:
    def publish(self, chat_message_doc, payload):
        try:
            chat_message_doc._publish_chat_realtime(
                event_name="cf_monitoring_update",
                payload={
                    "message_id": chat_message_doc.name,
                    "chat_id": chat_message_doc.chat,
                    "status": "monitoring",
                    "monitoring": payload,
                },
            )
            return {"published": True}
        except Exception:
            return {"published": False}


class UsageAnalytics:
    def summarize_last_days(self, days=30):
        from_date = frappe.utils.add_days(frappe.utils.nowdate(), -int(days or 30))

        rows = frappe.db.sql(
            """
            SELECT
              metric_date,
              SUM(messages) AS messages,
              AVG(quality_score) AS avg_quality,
              SUM(estimated_cost_usd) AS total_cost
            FROM `tabCF Quality Metric`
            WHERE metric_date >= %s
            GROUP BY metric_date
            ORDER BY metric_date ASC
            """,
            (from_date,),
            as_dict=True,
        ) if frappe.db.exists("DocType", "CF Quality Metric") else []

        return {
            "from_date": from_date,
            "days": int(days or 30),
            "rows": rows,
        }

# pyright: reportMissingImports=false
import csv
import hashlib
import io
import re

import frappe


class ContentSanitizer:
    SCRIPT_RE = re.compile(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", re.IGNORECASE)
    TAG_RE = re.compile(r"<[^>]+>")

    def sanitize_text(self, value):
        text = str(value or "")
        text = self.SCRIPT_RE.sub("", text)
        text = text.replace("javascript:", "")
        text = self.TAG_RE.sub("", text)

        # Preserve model formatting (newlines/headings/lists) while normalizing noisy spacing.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized_lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]

        # Trim leading/trailing empty lines and collapse long empty runs.
        while normalized_lines and normalized_lines[0] == "":
            normalized_lines.pop(0)
        while normalized_lines and normalized_lines[-1] == "":
            normalized_lines.pop()

        collapsed = []
        previous_blank = False
        for line in normalized_lines:
            is_blank = line == ""
            if is_blank and previous_blank:
                continue
            collapsed.append(line)
            previous_blank = is_blank

        return "\n".join(collapsed)

    def sanitize_result_items(self, items):
        sanitized = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["title"] = self.sanitize_text(row.get("title"))
            row["snippet"] = self.sanitize_text(row.get("snippet"))
            sanitized.append(row)
        return sanitized


class PrivacyPreserver:
    EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    PHONE_RE = re.compile(r"\+?[0-9][0-9\-() ]{7,}[0-9]")

    def anonymize_query(self, query):
        text = str(query or "")
        text = self.EMAIL_RE.sub("[redacted-email]", text)
        text = self.PHONE_RE.sub("[redacted-phone]", text)
        return text

    def fingerprint(self, text):
        return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:24]


class AccessControl:
    FEATURE_ROLE_MAP = {
        "search": {"System Manager", "Portfolio Manager"},
        "export_compliance": {"System Manager"},
        "experiment_admin": {"System Manager"},
    }

    def has_access(self, feature, user=None):
        user_id = user or frappe.session.user
        allowed_roles = self.FEATURE_ROLE_MAP.get(str(feature or "").strip().lower(), set())
        if not allowed_roles:
            return True

        roles = set(frappe.get_roles(user_id) or [])
        return bool(roles.intersection(allowed_roles))


class AuditLogger:
    DOCTYPE_NAME = "CF Access Audit"

    def log(self, event_name, status="success", details=None, user=None, chat=None, message=None):
        if not frappe.db.exists("DocType", self.DOCTYPE_NAME):
            return {"logged": False, "reason": "doctype_missing"}

        payload = {
            "doctype": self.DOCTYPE_NAME,
            "event_name": str(event_name or "").strip()[:140],
            "status": str(status or "").strip().lower()[:20],
            "details_json": frappe.as_json(details or {}),
            "user": user or frappe.session.user,
            "chat": chat,
            "chat_message": message,
        }
        try:
            doc = frappe.get_doc(payload)
            doc.insert(ignore_permissions=True)
            return {"logged": True, "name": doc.name}
        except Exception:
            frappe.log_error(title="AuditLogger error", message=frappe.get_traceback())
            return {"logged": False, "reason": "insert_failed"}


class SearchComplianceTracker:
    DOCTYPE_NAME = "CF Search Compliance Log"

    def record_search(self, query, query_type, providers, result_count, metadata=None):
        if not frappe.db.exists("DocType", self.DOCTYPE_NAME):
            return {"logged": False, "reason": "doctype_missing"}

        metadata = metadata or {}
        privacy = PrivacyPreserver()
        redacted_query = privacy.anonymize_query(query)
        query_fp = privacy.fingerprint(query)
        violations = self._detect_violations(redacted_query)

        payload = {
            "doctype": self.DOCTYPE_NAME,
            "log_date": frappe.utils.nowdate(),
            "query_fingerprint": query_fp,
            "query_redacted": redacted_query[:500],
            "query_type": str(query_type or "general")[:40],
            "providers": ",".join(sorted({str(x).strip().lower() for x in (providers or []) if str(x).strip()}))[:200],
            "result_count": int(result_count or 0),
            "violation_count": len(violations),
            "violations_json": frappe.as_json(violations),
            "metadata_json": frappe.as_json(metadata),
            "user": frappe.session.user,
            "chat": metadata.get("chat"),
            "chat_message": metadata.get("message"),
        }

        try:
            doc = frappe.get_doc(payload)
            doc.insert(ignore_permissions=True)
            return {"logged": True, "name": doc.name, "violation_count": len(violations)}
        except Exception:
            frappe.log_error(title="SearchComplianceTracker error", message=frappe.get_traceback())
            return {"logged": False, "reason": "insert_failed"}

    def _detect_violations(self, query):
        lowered = str(query or "").lower()
        findings = []
        if "insider" in lowered and "non-public" in lowered:
            findings.append("potential_mnpi")
        if "bypass" in lowered and "compliance" in lowered:
            findings.append("compliance_bypass_request")
        return findings


class DataRetentionPolicy:
    TARGETS = {
        "CF Search Compliance Log": "compliance_retention_days",
        "CF Access Audit": "audit_retention_days",
        "CF Quality Metric": "quality_retention_days",
        "CF User Feedback": "feedback_retention_days",
        "CF Monitoring Alert": "alert_retention_days",
        "CF Experiment Metric": "experiment_metric_retention_days",
    }

    def cleanup(self, config=None):
        config = config or {}
        deleted = {}

        for doctype, key in self.TARGETS.items():
            if not frappe.db.exists("DocType", doctype):
                continue

            days = max(7, int(config.get(key, 365) or 365))
            cutoff = frappe.utils.add_days(frappe.utils.nowdate(), -days)
            names = frappe.get_all(doctype, filters={"creation": ["<", cutoff]}, pluck="name", limit_page_length=5000)
            count = 0
            for name in names:
                try:
                    frappe.delete_doc(doctype, name, ignore_permissions=True, force=1)
                    count += 1
                except Exception:
                    continue
            deleted[doctype] = count

        if deleted:
            frappe.db.commit()

        return {"deleted": deleted, "total_deleted": sum(deleted.values())}


class ExportCapabilities:
    DOCTYPE_NAME = "CF Search Compliance Log"

    def export_compliance_logs_csv(self, from_date=None, to_date=None):
        if not frappe.db.exists("DocType", self.DOCTYPE_NAME):
            return ""

        filters = {}
        if from_date:
            filters["log_date"] = [">=", from_date]
        if to_date:
            if "log_date" in filters:
                filters["log_date"] = ["between", [from_date, to_date]]
            else:
                filters["log_date"] = ["<=", to_date]

        rows = frappe.get_all(
            self.DOCTYPE_NAME,
            filters=filters,
            fields=[
                "name",
                "log_date",
                "query_fingerprint",
                "query_type",
                "providers",
                "result_count",
                "violation_count",
                "user",
                "chat",
                "chat_message",
            ],
            order_by="creation desc",
            limit_page_length=20000,
        )

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "name", "log_date", "query_fingerprint", "query_type", "providers", "result_count", "violation_count", "user", "chat", "chat_message"
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

        return output.getvalue()

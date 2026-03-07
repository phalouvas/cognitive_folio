from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

from cognitive_folio.cognitive_folio.services.tooling import ToolMetricsStore


class TestToolMetricsStore(unittest.TestCase):
    def test_returns_doctype_missing(self):
        store = ToolMetricsStore()
        with patch("frappe.db.exists", return_value=False):
            result = store.persist_daily_rollups({"web_search": {"calls": 1}}, context={})
        self.assertFalse(result["persisted"])
        self.assertEqual(result["reason"], "doctype_missing")

    def test_inserts_new_daily_row(self):
        store = ToolMetricsStore()
        fake_doc = MagicMock()
        fake_doc.insert.return_value = None

        def fake_exists(doctype, name):
            if doctype == "DocType" and name == "CF Tool Metric":
                return True
            return False

        with patch("frappe.db.exists", side_effect=fake_exists), patch("frappe.db.get_value", return_value=None), patch(
            "frappe.get_doc", return_value=fake_doc
        ):
            result = store.persist_daily_rollups(
                {
                    "web_search": {
                        "calls": 2,
                        "success": 2,
                        "failure": 0,
                        "retries": 1,
                        "avg_duration_ms": 33.4,
                    }
                },
                context={
                    "metric_date": "2026-03-06",
                    "model": "deepseek-chat",
                    "intent": "general_research",
                    "chat": "CHAT-1",
                    "message": "MSG-1",
                },
            )

        self.assertTrue(result["persisted"])
        fake_doc.insert.assert_called_once()

    def test_updates_existing_daily_row(self):
        store = ToolMetricsStore()
        existing = SimpleNamespace(
            calls=3,
            success_count=2,
            failure_count=1,
            retry_count=0,
            avg_duration_ms=10.0,
            success_rate=0.6667,
            save=MagicMock(),
        )

        def fake_exists(doctype, name):
            if doctype == "DocType" and name == "CF Tool Metric":
                return True
            return False

        with patch("frappe.db.exists", side_effect=fake_exists), patch("frappe.db.get_value", return_value="METRIC-001"), patch(
            "frappe.get_doc", return_value=existing
        ):
            result = store.persist_daily_rollups(
                {"web_search": {"calls": 1, "success": 1, "failure": 0, "retries": 0, "avg_duration_ms": 30.0}},
                context={"metric_date": "2026-03-06", "model": "deepseek-chat", "intent": "general_research"},
            )

        self.assertTrue(result["persisted"])
        self.assertEqual(existing.calls, 4)
        self.assertEqual(existing.success_count, 3)
        existing.save.assert_called_once()
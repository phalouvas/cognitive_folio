from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

from cognitive_folio.cognitive_folio.services.memory.cleanup_metrics_store import CleanupMetricsStore


class TestCleanupMetricsStore(unittest.TestCase):
    def test_returns_doctype_missing(self):
        store = CleanupMetricsStore()
        with patch("frappe.db.exists", return_value=False):
            result = store.persist_daily({"pruned": True, "deleted": 2, "chats": 1})
        self.assertFalse(result["persisted"])
        self.assertEqual(result["reason"], "doctype_missing")

    def test_inserts_new_daily_metric(self):
        store = CleanupMetricsStore()
        fake_doc = MagicMock()

        def fake_exists(doctype, name):
            return doctype == "DocType" and name == "CF Memory Cleanup Metric"

        with patch("frappe.db.exists", side_effect=fake_exists), patch("frappe.db.get_value", return_value=None), patch(
            "frappe.get_doc", return_value=fake_doc
        ):
            result = store.persist_daily(
                {"pruned": True, "deleted": 7, "chats": 3},
                context={"metric_date": "2026-03-06", "run_at": "2026-03-06 05:00:00"},
            )

        self.assertTrue(result["persisted"])
        fake_doc.insert.assert_called_once()

    def test_updates_existing_daily_metric(self):
        store = CleanupMetricsStore()
        existing = SimpleNamespace(
            runs=2,
            success_runs=1,
            failed_runs=1,
            chats_scanned=5,
            rows_deleted=9,
            save=MagicMock(),
        )

        def fake_exists(doctype, name):
            return doctype == "DocType" and name == "CF Memory Cleanup Metric"

        with patch("frappe.db.exists", side_effect=fake_exists), patch("frappe.db.get_value", return_value="MCLN-0001"), patch(
            "frappe.get_doc", return_value=existing
        ):
            result = store.persist_daily(
                {"pruned": False, "deleted": 2, "chats": 4, "reason": "task_failed"},
                context={"metric_date": "2026-03-06", "run_at": "2026-03-06 05:00:00"},
            )

        self.assertTrue(result["persisted"])
        self.assertEqual(existing.runs, 3)
        self.assertEqual(existing.failed_runs, 2)
        self.assertEqual(existing.rows_deleted, 11)
        existing.save.assert_called_once()

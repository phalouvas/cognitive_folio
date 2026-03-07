import unittest
from unittest.mock import MagicMock, patch

from cognitive_folio import tasks


class TestScheduledTasks(unittest.TestCase):
    def test_cleanup_vector_memory_store_runs_prune(self):
        settings_doc = MagicMock()
        vector_memory = MagicMock()
        metrics_store = MagicMock()
        vector_memory.prune_persistent_store.return_value = {
            "pruned": True,
            "deleted": 4,
            "chats": 2,
        }

        with patch("cognitive_folio.tasks.frappe.get_cached_doc", return_value=settings_doc), patch(
            "cognitive_folio.tasks.SettingsManager"
        ) as settings_manager_cls, patch("cognitive_folio.tasks.VectorMemory", return_value=vector_memory), patch(
            "cognitive_folio.tasks.CleanupMetricsStore", return_value=metrics_store
        ), patch("cognitive_folio.tasks.frappe.db.commit"
        ) as commit_mock:
            settings_manager_cls.return_value.get_memory_config.return_value = {
                "vector_persist_enabled": True,
                "vector_store_max_records_per_chat": 300,
                "vector_store_max_age_days": 180,
            }

            result = tasks.cleanup_vector_memory_store()

        self.assertTrue(result.get("pruned"))
        self.assertEqual(result.get("deleted"), 4)
        vector_memory.prune_persistent_store.assert_called_once()
        metrics_store.persist_daily.assert_called_once_with(result)
        commit_mock.assert_called_once()

    def test_cleanup_vector_memory_store_handles_failures(self):
        metrics_store = MagicMock()
        with patch("cognitive_folio.tasks.frappe.get_cached_doc", side_effect=Exception("boom")), patch(
            "cognitive_folio.tasks.CleanupMetricsStore", return_value=metrics_store
        ):
            result = tasks.cleanup_vector_memory_store()

        self.assertFalse(result.get("pruned"))
        self.assertEqual(result.get("reason"), "task_failed")
        metrics_store.persist_daily.assert_called_once()

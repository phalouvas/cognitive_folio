import unittest
from unittest.mock import MagicMock, patch

from cognitive_folio.cognitive_folio.services.memory.vector_memory import VectorMemory


class DummyCache:
    def __init__(self):
        self.store = {}

    def get_value(self, key):
        return self.store.get(key)

    def set_value(self, key, value):
        self.store[key] = value


class TestVectorMemory(unittest.TestCase):
    def test_record_and_get_context_with_security_filter(self):
        memory = VectorMemory()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            memory.record_turn(
                chat_name="CHAT-VM-1",
                prompt="Review AAPL downside risk",
                response="AAPL drawdown risk is moderate due to valuation compression.",
                config={"vector_enabled": True, "vector_cache_items": 20},
                metadata={"facts": ["AAPL risk profile updated"]},
                context={"portfolio": "PORT-1", "security": "SEC-AAPL"},
            )
            memory.record_turn(
                chat_name="CHAT-VM-1",
                prompt="Review TSLA momentum",
                response="TSLA has stronger momentum but higher volatility.",
                config={"vector_enabled": True, "vector_cache_items": 20},
                metadata={"facts": ["TSLA momentum reviewed"]},
                context={"portfolio": "PORT-1", "security": "SEC-TSLA"},
            )

            context = memory.get_context(
                chat_name="CHAT-VM-1",
                current_prompt="Need latest AAPL risk view",
                config={"vector_enabled": True, "vector_max_items": 1, "vector_max_chars": 800},
                context={"portfolio": "PORT-1", "security": "SEC-AAPL"},
            )

        self.assertIn("SEC-AAPL", context)
        self.assertIn("AAPL", context)

    def test_vector_can_be_disabled(self):
        memory = VectorMemory()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            result = memory.record_turn(
                chat_name="CHAT-VM-2",
                prompt="prompt",
                response="response",
                config={"vector_enabled": False},
                metadata={},
                context={},
            )
            context = memory.get_context(
                chat_name="CHAT-VM-2",
                current_prompt="prompt",
                config={"vector_enabled": False},
                context={},
            )

        self.assertFalse(result["stored"])
        self.assertEqual(result["reason"], "vector_disabled")
        self.assertEqual(context, "")

    def test_embedding_mode_prefers_semantic_similarity(self):
        memory = VectorMemory()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            memory.record_turn(
                chat_name="CHAT-VM-3",
                prompt="Assess volatility in TSLA",
                response="TSLA volatility remains elevated during rapid repricing.",
                config={"vector_enabled": True, "vector_cache_items": 20, "vector_similarity_mode": "embedding"},
                metadata={"facts": ["TSLA volatility elevated"]},
                context={"portfolio": "PORT-1", "security": "SEC-TSLA"},
            )
            memory.record_turn(
                chat_name="CHAT-VM-3",
                prompt="Evaluate dividend schedule for KO",
                response="KO dividend cadence is stable.",
                config={"vector_enabled": True, "vector_cache_items": 20, "vector_similarity_mode": "embedding"},
                metadata={"facts": ["KO dividends stable"]},
                context={"portfolio": "PORT-1", "security": "SEC-KO"},
            )

            context = memory.get_context(
                chat_name="CHAT-VM-3",
                current_prompt="Need a volatile TSLA risk update",
                config={"vector_enabled": True, "vector_max_items": 1, "vector_similarity_mode": "embedding"},
                context={"portfolio": "PORT-1"},
            )

        self.assertIn("TSLA", context)

    def test_lexical_mode_still_supported(self):
        memory = VectorMemory()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            memory.record_turn(
                chat_name="CHAT-VM-4",
                prompt="Need earnings summary for NVDA",
                response="NVDA beat consensus estimates.",
                config={"vector_enabled": True, "vector_similarity_mode": "lexical"},
                metadata={},
                context={},
            )
            context = memory.get_context(
                chat_name="CHAT-VM-4",
                current_prompt="Provide NVDA earnings view",
                config={"vector_enabled": True, "vector_similarity_mode": "lexical", "vector_max_items": 1},
                context={},
            )

        self.assertIn("NVDA", context)

    def test_persistence_writes_when_doctype_available(self):
        memory = VectorMemory()
        cache = DummyCache()

        fake_doc = MagicMock()
        fake_doc.name = "VMEM-0001"
        fake_doc.insert.return_value = None

        def fake_exists(doctype, name):
            return doctype == "DocType" and name == "CF Vector Memory"

        with patch("frappe.cache", return_value=cache), patch("frappe.db.exists", side_effect=fake_exists), patch(
            "frappe.get_doc", return_value=fake_doc
        ), patch.object(VectorMemory, "_prune_store", return_value={"deleted": 0}):
            result = memory.record_turn(
                chat_name="CHAT-VM-5",
                prompt="Track AAPL volatility",
                response="AAPL volatility increased this week.",
                config={"vector_enabled": True, "vector_persist_enabled": True},
                metadata={"facts": ["AAPL volatility up"]},
                context={"portfolio": "PORT-1", "security": "SEC-AAPL"},
            )

        self.assertTrue(result["stored"])
        self.assertTrue((result.get("persistence") or {}).get("persisted"))
        fake_doc.insert.assert_called_once()

    def test_prune_store_deletes_overflow_and_expired_rows(self):
        memory = VectorMemory()

        def fake_exists(doctype, name):
            return doctype == "DocType" and name == "CF Vector Memory"

        calls = {"count": 0}

        def fake_get_all(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return [{"name": "VM-003"}, {"name": "VM-004"}]
            return [{"name": "VM-001"}]

        deleted = []

        def fake_delete_doc(doctype, name, ignore_permissions=True, force=1):
            deleted.append((doctype, name))

        with patch("frappe.db.exists", side_effect=fake_exists), patch("frappe.get_all", side_effect=fake_get_all), patch(
            "frappe.delete_doc", side_effect=fake_delete_doc
        ), patch("frappe.utils.nowdate", return_value="2026-03-06"), patch("frappe.utils.add_days", return_value="2025-09-07"):
            result = memory._prune_store(
                chat_name="CHAT-VM-7",
                config={
                    "vector_persist_enabled": True,
                    "vector_store_max_records_per_chat": 2,
                    "vector_store_max_age_days": 180,
                },
            )

        self.assertEqual(result.get("deleted"), 3)
        self.assertIn(("CF Vector Memory", "VM-003"), deleted)
        self.assertIn(("CF Vector Memory", "VM-004"), deleted)
        self.assertIn(("CF Vector Memory", "VM-001"), deleted)

    def test_prune_persistent_store_prunes_all_chat_groups(self):
        memory = VectorMemory()

        def fake_exists(doctype, name):
            return doctype == "DocType" and name == "CF Vector Memory"

        chat_rows = [{"chat": "CHAT-1"}, {"chat": "CHAT-2"}]

        with patch("frappe.db.exists", side_effect=fake_exists), patch("frappe.get_all", return_value=chat_rows), patch.object(
            VectorMemory,
            "_prune_store",
            side_effect=[{"deleted": 2}, {"deleted": 3}],
        ) as prune_mock:
            result = memory.prune_persistent_store(
                config={"vector_persist_enabled": True, "vector_store_max_records_per_chat": 100, "vector_store_max_age_days": 180}
            )

        self.assertTrue(result.get("pruned"))
        self.assertEqual(result.get("chats"), 2)
        self.assertEqual(result.get("deleted"), 5)
        self.assertEqual(prune_mock.call_count, 2)

    def test_store_fallback_loads_entries_when_cache_empty(self):
        memory = VectorMemory()
        cache = DummyCache()

        rows = [
            {
                "memory_text": "AAPL drawdown risk is moderate.",
                "facts_json": '["AAPL risk updated"]',
                "tags_json": '["AAPL"]',
                "embedding_json": "[]",
                "portfolio": "PORT-1",
                "security": "SEC-AAPL",
            }
        ]

        def fake_exists(doctype, name):
            return doctype == "DocType" and name == "CF Vector Memory"

        with patch("frappe.cache", return_value=cache), patch("frappe.db.exists", side_effect=fake_exists), patch(
            "frappe.get_all", return_value=rows
        ):
            context = memory.get_context(
                chat_name="CHAT-VM-6",
                current_prompt="Need AAPL risk summary",
                config={"vector_enabled": True, "vector_persist_enabled": True, "vector_max_items": 1},
                context={"portfolio": "PORT-1", "security": "SEC-AAPL"},
            )

        self.assertIn("AAPL", context)

    def test_db_fallback_handles_missing_portfolio_columns(self):
        memory = VectorMemory()

        rows = [{"prompt": "Check NVDA news", "response": "NVDA outlook remains strong."}]

        with patch("frappe.get_all", side_effect=[Exception("Unknown column 'portfolio' in 'SELECT'"), rows]):
            entries = memory._load_recent_entries_from_db(chat_name="CHAT-VM-DB", limit=5)

        self.assertEqual(len(entries), 1)
        self.assertIn("NVDA", entries[0].get("text") or "")
        self.assertIsNone(entries[0].get("portfolio"))
        self.assertIsNone(entries[0].get("security"))

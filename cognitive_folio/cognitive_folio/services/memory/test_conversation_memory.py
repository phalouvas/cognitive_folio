import unittest
from unittest.mock import patch

from cognitive_folio.cognitive_folio.services.memory.conversation_memory import ConversationMemory


class DummyCache:
    def __init__(self):
        self.store = {}

    def get_value(self, key):
        return self.store.get(key)

    def set_value(self, key, value):
        self.store[key] = value


class TestConversationMemory(unittest.TestCase):
    def test_record_and_read_from_cache(self):
        memory = ConversationMemory()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            result = memory.record_turn(
                chat_name="CHAT-1",
                prompt="Track AAPL and MSFT over next quarter",
                response="Noted. We will watch AAPL and MSFT earnings dates.",
                config={"cache_items": 10},
            )
            context = memory.get_context("CHAT-1", config={"max_items": 5, "max_chars": 1000})

        self.assertTrue(result["stored"])
        self.assertIn("AAPL", context)
        self.assertIn("MSFT", context)

    def test_db_fallback_when_cache_empty(self):
        memory = ConversationMemory()
        cache = DummyCache()

        rows = [
            {"prompt": "Review NVDA position", "response": "NVDA position is profitable."},
        ]

        with patch("frappe.cache", return_value=cache), patch("frappe.get_all", return_value=rows):
            context = memory.get_context("CHAT-2", config={"max_items": 5, "max_chars": 1000})

        self.assertIn("NVDA", context)

    def test_context_is_bounded(self):
        memory = ConversationMemory()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            memory.record_turn(
                chat_name="CHAT-3",
                prompt="x" * 500,
                response="y" * 500,
                config={"cache_items": 10},
            )
            context = memory.get_context("CHAT-3", config={"max_items": 5, "max_chars": 120})

        self.assertLessEqual(len(context), 120)

    def test_relevance_selects_matching_memory(self):
        memory = ConversationMemory()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            memory.record_turn(
                chat_name="CHAT-4",
                prompt="Discuss TSLA valuation",
                response="TSLA appears expensive against current growth expectations.",
                config={"cache_items": 20},
                metadata={"facts": ["Ticker TSLA under review"]},
            )
            memory.record_turn(
                chat_name="CHAT-4",
                prompt="Summarize bond ladder",
                response="Bond ladder has lower volatility than equities.",
                config={"cache_items": 20},
            )

            context = memory.get_context(
                "CHAT-4",
                config={"max_items": 1, "max_chars": 1000, "max_relevant_items": 1},
                current_prompt="Need an updated TSLA risk view",
            )

        self.assertIn("TSLA", context)
        self.assertIn("Facts:", context)

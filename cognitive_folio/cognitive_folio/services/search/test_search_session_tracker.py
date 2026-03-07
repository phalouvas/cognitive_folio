import unittest
from unittest.mock import patch

from cognitive_folio.cognitive_folio.services.search import SearchSessionTracker


class DummyCache:
    def __init__(self):
        self.store = {}

    def get_value(self, key):
        return self.store.get(key)

    def set_value(self, key, value):
        self.store[key] = value


class TestSearchSessionTracker(unittest.TestCase):
    def test_record_search_persists_history(self):
        tracker = SearchSessionTracker()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            result = tracker.record_search(
                session_key="CHAT-1",
                query="tsla earnings outlook",
                query_type="financial",
                providers=["ddgs"],
                results=[{"url": "https://example.com/a"}],
                max_entries=10,
            )

        self.assertTrue(result["stored"])
        self.assertEqual(result["items"], 1)

    def test_expand_follow_up_query_uses_recent_topic(self):
        tracker = SearchSessionTracker()
        cache = DummyCache()

        with patch("frappe.cache", return_value=cache):
            tracker.record_search(
                session_key="CHAT-2",
                query="tsla earnings beat expectations",
                query_type="financial",
                providers=["ddgs"],
                results=[{"url": "https://example.com/a"}],
            )
            expanded = tracker.expand_follow_up_query("what about it", session_key="CHAT-2")

        self.assertIn("about tsla earnings beat expectations", expanded)

    def test_expand_follow_up_query_keeps_specific_query(self):
        tracker = SearchSessionTracker()

        expanded = tracker.expand_follow_up_query("nvda guidance changes", session_key="CHAT-3")

        self.assertEqual(expanded, "nvda guidance changes")

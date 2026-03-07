import unittest

from cognitive_folio.cognitive_folio.services.tooling.plugins.basic_tools import (
    get_tool_definitions,
    handle_normalize_ticker,
)


class TestBasicToolsPlugin(unittest.TestCase):
    def test_get_tool_definitions_contains_normalize_ticker(self):
        tools = get_tool_definitions()
        names = [((item or {}).get("function") or {}).get("name") for item in tools]
        self.assertIn("normalize_ticker", names)

    def test_handle_normalize_ticker(self):
        result = handle_normalize_ticker(None, {"ticker": " aapl.us "})
        self.assertEqual(result["normalized"], "AAPL.US")
        self.assertTrue(result["changed"])
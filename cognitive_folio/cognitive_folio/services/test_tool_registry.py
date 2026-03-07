from unittest.mock import MagicMock, patch
import unittest

from cognitive_folio.cognitive_folio.services.tooling import ToolRegistry


class TestToolRegistry(unittest.TestCase):
    def test_merge_tool_definitions_adds_hook_tools(self):
        chat_message = MagicMock()
        registry = ToolRegistry(chat_message)
        base = [{"type": "function", "function": {"name": "web_search"}}]
        dynamic = [{"type": "function", "function": {"name": "normalize_ticker"}}]

        with patch("frappe.get_hooks", return_value=["path.to.definitions"]), patch(
            "frappe.get_attr", return_value=lambda *_args, **_kwargs: dynamic
        ):
            merged = registry.merge_tool_definitions(base)

        names = [((tool or {}).get("function") or {}).get("name") for tool in merged]
        self.assertIn("web_search", names)
        self.assertIn("normalize_ticker", names)

    def test_get_dynamic_handlers_resolves_hook_callables(self):
        chat_message = MagicMock()
        registry = ToolRegistry(chat_message)

        def handler(args):
            return args

        with patch("frappe.get_hooks", return_value={"normalize_ticker": "path.to.handler"}), patch(
            "frappe.get_attr", return_value=handler
        ):
            handlers = registry.get_dynamic_handlers()

        self.assertIn("normalize_ticker", handlers)
        self.assertTrue(callable(handlers["normalize_ticker"]))
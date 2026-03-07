# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

import unittest
from unittest.mock import MagicMock, patch

from cognitive_folio.cognitive_folio.doctype.cf_chat_message.cf_chat_message import (
    CFChatMessage,
    DEEPSEEK_CHAT_MAX_TOKENS_CAP,
)
from cognitive_folio.cognitive_folio.services.token_manager import TokenManager
from cognitive_folio.cognitive_folio.services.web_search_service import (
    FINANCIAL_QUERY_KEYWORDS,
    WebSearchService,
)


def _make_doc():
    """Create a minimal CFChatMessage instance without database access."""
    doc = CFChatMessage.__new__(CFChatMessage)
    doc.name = "test-msg-001"
    doc.chat = "test-chat-001"
    doc.model = "deepseek-chat"
    doc.prompt = "test prompt"
    doc.web_search = False
    doc.fetch_urls = False
    return doc


class TestCFChatMessageSearchHelpers(unittest.TestCase):
    """Unit tests for pure logic helper services and tool methods."""

    def test_count_markdown_results(self):
        token_manager = TokenManager(_make_doc())
        md = "1. First result\n2. Second result\n3. Third result"
        self.assertEqual(token_manager.count_markdown_search_results(md), 3)
        self.assertEqual(token_manager.count_markdown_search_results(""), 0)
        self.assertEqual(token_manager.count_markdown_search_results(None), 0)

    def test_classify_query_type(self):
        service = WebSearchService(_make_doc())
        self.assertEqual(service.classify_query_type("Apple AAPL stock earnings"), "financial")
        self.assertEqual(service.classify_query_type("how to cook pasta"), "general")
        self.assertEqual(service.classify_query_type(""), "general")

    def test_deduplicate_results(self):
        service = WebSearchService(_make_doc())
        deduped = service.deduplicate_results([
            {"url": "https://example.com/page/", "title": "A"},
            {"url": "https://example.com/page", "title": "A dup"},
            {"url": "", "title": "No URL"},
            {"url": "https://example.com/other", "title": "B"},
        ])
        self.assertEqual(len(deduped), 2)

    def test_tool_web_search_validation_and_providers_used(self):
        doc = _make_doc()
        service = WebSearchService(doc)
        doc._web_search_service = service

        with self.assertRaises(ValueError):
            doc._tool_web_search({"query": ""})

        with patch.object(service, "search_web_results", return_value=[{"source": "ddgs", "url": "https://a.com"}]):
            result = doc._tool_web_search({"query": "AAPL earnings"})
        self.assertIn("ddgs", result["providers_used"])

    def test_tool_search_financial_passes_ticker(self):
        doc = _make_doc()
        service = WebSearchService(doc)
        doc._web_search_service = service
        captured = {}

        def fake_search_financial_sources(**kwargs):
            captured.update(kwargs)
            return []

        with patch.object(service, "search_financial_sources", side_effect=fake_search_financial_sources):
            doc._tool_search_financial({"query": "Apple earnings", "ticker": "AAPL"})

        self.assertEqual(captured.get("ticker"), "AAPL")

    def test_search_web_results_auto_provider_selection(self):
        service = WebSearchService(_make_doc())
        service.prefetching.enabled = False

        with patch.object(service.provider_registry, "resolve_chain", return_value=["ddgs", "wikipedia"]) as mock_resolve, patch.object(service, "_execute_provider_search", return_value=[]) as mock_exec:
            service.search_web_results("history of the Roman Empire")
        mock_resolve.assert_called_once_with(provider_hint="auto", query_type="general")
        providers = [call.kwargs.get("provider") for call in mock_exec.call_args_list]
        self.assertEqual(providers, ["ddgs", "wikipedia"])

        with patch.object(service.provider_registry, "resolve_chain", return_value=["ddgs", "sec_edgar"]) as mock_resolve, patch.object(service, "_execute_provider_search", return_value=[]) as mock_exec:
            service.search_web_results("Apple AAPL stock earnings 10-K")
        mock_resolve.assert_called_once_with(provider_hint="auto", query_type="financial")
        providers = [call.kwargs.get("provider") for call in mock_exec.call_args_list]
        self.assertEqual(providers, ["ddgs", "sec_edgar"])

    def test_search_financial_sources_routing(self):
        service = WebSearchService(_make_doc())
        service.prefetching.enabled = False

        with patch.object(service.provider_registry, "resolve_chain", return_value=["ddgs", "sec_edgar", "financial_news"]) as mock_resolve, patch.object(service, "_execute_provider_search", return_value=[]) as mock_exec:
            service.search_financial_sources("Apple revenue", source="auto")
        mock_resolve.assert_called_once_with(provider_hint="auto", query_type="financial")
        providers = [call.kwargs.get("provider") for call in mock_exec.call_args_list]
        self.assertEqual(providers, ["ddgs", "sec_edgar", "financial_news"])

        service = WebSearchService(_make_doc())
        service.prefetching.enabled = False
        with patch.object(service.provider_registry, "resolve_chain", return_value=["sec_edgar"]) as mock_resolve, patch.object(service, "_execute_provider_search", return_value=[]) as mock_exec:
            service.search_financial_sources("10-K", source="sec_edgar")
        mock_resolve.assert_called_once_with(provider_hint="sec_edgar", query_type="financial")
        providers = [call.kwargs.get("provider") for call in mock_exec.call_args_list]
        self.assertEqual(providers, ["sec_edgar"])

    def test_financial_keywords_constant(self):
        self.assertIsInstance(FINANCIAL_QUERY_KEYWORDS, frozenset)
        for term in ("stock", "earnings", "10-k", "sec", "edgar", "dividend"):
            self.assertIn(term, FINANCIAL_QUERY_KEYWORDS)

class TestCFChatMessageTokenAndThinkingModes(unittest.TestCase):
    def test_deepseek_chat_with_thinking_uses_chat_token_limits(self):
        doc = _make_doc()
        doc.model = "deepseek-chat"

        settings = MagicMock()

        def fake_get(fieldname):
            mapping = {
                "thinking_enabled": "1",
                "reasoner_default_max_tokens": "32000",
                "reasoner_max_tokens_cap": "64000",
                "chat_default_max_tokens": "7000",
                "chat_max_tokens_cap": "8000",
            }
            return mapping.get(fieldname)

        settings.get.side_effect = fake_get

        tokens = doc._get_max_completion_tokens(settings, "quick question")

        self.assertEqual(tokens, 7000)

    def test_deepseek_chat_tokens_hard_clamped_to_provider_limit(self):
        doc = _make_doc()
        doc.model = "deepseek-chat"

        settings = MagicMock()

        def fake_get(fieldname):
            mapping = {
                "chat_default_max_tokens": "50000",
                "chat_max_tokens_cap": "50000",
            }
            return mapping.get(fieldname)

        settings.get.side_effect = fake_get

        tokens = doc._get_max_completion_tokens(settings, "test")

        self.assertEqual(tokens, DEEPSEEK_CHAT_MAX_TOKENS_CAP)

    def test_thinking_mode_active_for_deepseek_chat_only_when_enabled(self):
        doc = _make_doc()
        doc.model = "deepseek-chat"

        settings = MagicMock()
        settings.get.return_value = "0"
        self.assertFalse(doc._is_thinking_mode_active(settings))

        settings.get.return_value = "1"
        self.assertTrue(doc._is_thinking_mode_active(settings))

    def test_thinking_mode_always_active_for_reasoner(self):
        doc = _make_doc()
        doc.model = "deepseek-reasoner"

        settings = MagicMock()
        settings.get.return_value = "0"

        self.assertTrue(doc._is_thinking_mode_active(settings))


class TestCFChatMessagePromptSensitivity(unittest.TestCase):
    def test_is_time_sensitive_prompt_for_weather(self):
        doc = _make_doc()
        self.assertTrue(doc._is_time_sensitive_prompt("What is the weather now in Larnaka Cyprus?"))

    def test_is_time_sensitive_prompt_for_geopolitical_timing(self):
        doc = _make_doc()
        self.assertTrue(doc._is_time_sensitive_prompt("How long will the war between Iran and Israel started in 2026 last?"))

    def test_is_time_sensitive_prompt_for_generic_finance(self):
        doc = _make_doc()
        self.assertFalse(doc._is_time_sensitive_prompt("Explain portfolio diversification principles."))

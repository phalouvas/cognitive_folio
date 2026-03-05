# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

# import frappe
from unittest.mock import MagicMock, patch
from frappe.tests.utils import FrappeTestCase

from cognitive_folio.cognitive_folio.doctype.cf_chat_message.cf_chat_message import (
	CFChatMessage,
	FINANCIAL_QUERY_KEYWORDS,
	DEFAULT_WEB_SEARCH_MAX_RESULTS,
	DEFAULT_WEB_SEARCH_PROVIDERS,
	DEEPSEEK_CHAT_MAX_TOKENS_CAP,
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


class TestCFChatMessageSearchHelpers(FrappeTestCase):
	"""Unit tests for pure-logic helper methods that do not require database access."""

	# ------------------------------------------------------------------
	# _count_markdown_search_results
	# ------------------------------------------------------------------

	def test_count_markdown_results_empty_string(self):
		doc = _make_doc()
		self.assertEqual(doc._count_markdown_search_results(""), 0)

	def test_count_markdown_results_none(self):
		doc = _make_doc()
		self.assertEqual(doc._count_markdown_search_results(None), 0)

	def test_count_markdown_results_numbered_list(self):
		doc = _make_doc()
		md = "1. First result\n2. Second result\n3. Third result"
		self.assertEqual(doc._count_markdown_search_results(md), 3)

	def test_count_markdown_results_no_numbers(self):
		doc = _make_doc()
		md = "Some text without numbered list"
		self.assertEqual(doc._count_markdown_search_results(md), 0)

	# ------------------------------------------------------------------
	# _classify_query_type
	# ------------------------------------------------------------------

	def test_classify_financial_keywords(self):
		doc = _make_doc()
		for query in [
			"Apple AAPL stock earnings",
			"SEC 10-K annual report",
			"EBITDA valuation analysis",
			"dividend yield bond",
			"IPO merger acquisition",
		]:
			with self.subTest(query=query):
				self.assertEqual(doc._classify_query_type(query), "financial")

	def test_classify_general_query(self):
		doc = _make_doc()
		for query in [
			"how to cook pasta",
			"best programming languages 2024",
			"weather forecast tomorrow",
		]:
			with self.subTest(query=query):
				self.assertEqual(doc._classify_query_type(query), "general")

	def test_classify_empty_query(self):
		doc = _make_doc()
		self.assertEqual(doc._classify_query_type(""), "general")
		self.assertEqual(doc._classify_query_type(None), "general")

	# ------------------------------------------------------------------
	# _deduplicate_results
	# ------------------------------------------------------------------

	def test_deduplicate_removes_exact_url_dupes(self):
		doc = _make_doc()
		results = [
			{"url": "https://example.com/a", "title": "A", "snippet": "A", "source": "ddgs"},
			{"url": "https://example.com/a", "title": "A copy", "snippet": "A", "source": "wikipedia"},
			{"url": "https://example.com/b", "title": "B", "snippet": "B", "source": "ddgs"},
		]
		deduped = doc._deduplicate_results(results)
		self.assertEqual(len(deduped), 2)
		self.assertEqual(deduped[0]["url"], "https://example.com/a")
		self.assertEqual(deduped[1]["url"], "https://example.com/b")

	def test_deduplicate_normalizes_trailing_slash(self):
		doc = _make_doc()
		results = [
			{"url": "https://example.com/page/", "title": "A", "snippet": "A", "source": "ddgs"},
			{"url": "https://example.com/page", "title": "A dup", "snippet": "A", "source": "ddgs"},
		]
		deduped = doc._deduplicate_results(results)
		self.assertEqual(len(deduped), 1)

	def test_deduplicate_skips_empty_url(self):
		doc = _make_doc()
		results = [
			{"url": "", "title": "No URL", "snippet": "X", "source": "ddgs"},
			{"url": "https://example.com/a", "title": "A", "snippet": "A", "source": "ddgs"},
		]
		deduped = doc._deduplicate_results(results)
		self.assertEqual(len(deduped), 1)
		self.assertEqual(deduped[0]["url"], "https://example.com/a")

	def test_deduplicate_empty_list(self):
		doc = _make_doc()
		self.assertEqual(doc._deduplicate_results([]), [])

	# ------------------------------------------------------------------
	# _get_web_search_max_results / _get_web_search_providers
	# ------------------------------------------------------------------

	def test_get_web_search_max_results_default(self):
		doc = _make_doc()
		settings = MagicMock()
		settings.get.return_value = None
		self.assertEqual(doc._get_web_search_max_results(settings), DEFAULT_WEB_SEARCH_MAX_RESULTS)

	def test_get_web_search_max_results_custom(self):
		doc = _make_doc()
		settings = MagicMock()
		settings.get.return_value = "8"
		self.assertEqual(doc._get_web_search_max_results(settings), 8)

	def test_get_web_search_providers_default(self):
		doc = _make_doc()
		settings = MagicMock()
		settings.get.return_value = None
		providers = doc._get_web_search_providers(settings)
		self.assertIn(DEFAULT_WEB_SEARCH_PROVIDERS, providers)

	def test_get_web_search_providers_custom(self):
		doc = _make_doc()
		settings = MagicMock()
		settings.get.return_value = "ddgs, wikipedia"
		providers = doc._get_web_search_providers(settings)
		self.assertEqual(providers, ["ddgs", "wikipedia"])

	# ------------------------------------------------------------------
	# _tool_web_search — validation
	# ------------------------------------------------------------------

	def test_tool_web_search_raises_on_empty_query(self):
		doc = _make_doc()
		with self.assertRaises(ValueError):
			doc._tool_web_search({"query": ""})

	def test_tool_web_search_raises_on_missing_query(self):
		doc = _make_doc()
		with self.assertRaises(ValueError):
			doc._tool_web_search({})

	def test_tool_web_search_clamps_max_results(self):
		doc = _make_doc()
		with patch.object(doc, "_search_web_results", return_value=[]) as mock_search:
			doc._tool_web_search({"query": "test", "max_results": 99})
			_args, _kwargs = mock_search.call_args
			# num_results should be clamped to 10
			self.assertLessEqual(_kwargs.get("num_results", _args[1] if len(_args) > 1 else 10), 10)

	def test_tool_web_search_returns_providers_used(self):
		doc = _make_doc()
		mock_results = [
			{"url": "https://a.com", "title": "A", "snippet": "snip", "source": "ddgs"},
		]
		with patch.object(doc, "_search_web_results", return_value=mock_results):
			result = doc._tool_web_search({"query": "AAPL earnings"})
		self.assertIn("providers_used", result)
		self.assertIn("ddgs", result["providers_used"])

	# ------------------------------------------------------------------
	# _tool_search_financial — validation
	# ------------------------------------------------------------------

	def test_tool_search_financial_raises_on_empty_query(self):
		doc = _make_doc()
		with self.assertRaises(ValueError):
			doc._tool_search_financial({"query": ""})

	def test_tool_search_financial_raises_on_missing_query(self):
		doc = _make_doc()
		with self.assertRaises(ValueError):
			doc._tool_search_financial({})

	def test_tool_search_financial_passes_ticker(self):
		doc = _make_doc()
		captured = {}

		def fake_search_financial(**kwargs):
			captured.update(kwargs)
			return []

		with patch.object(doc, "_search_financial_sources", side_effect=fake_search_financial):
			doc._tool_search_financial({"query": "Apple earnings", "ticker": "AAPL"})

		self.assertEqual(captured.get("ticker"), "AAPL")

	def test_tool_search_financial_returns_expected_keys(self):
		doc = _make_doc()
		with patch.object(doc, "_search_financial_sources", return_value=[]):
			result = doc._tool_search_financial({"query": "Apple 10-K"})
		for key in ("query", "ticker", "source", "count", "providers_used", "results"):
			self.assertIn(key, result)

	# ------------------------------------------------------------------
	# _search_web_results with mocked providers
	# ------------------------------------------------------------------

	def test_search_web_results_auto_selects_ddgs_only_for_financial(self):
		doc = _make_doc()

		def fake_search_ddgs(query, max_results=5, date_range=None, domain_filter=None):
			return [{"url": "https://sec.gov/1", "title": "SEC", "snippet": "sec", "source": "ddgs"}]

		with patch.object(doc, "_search_ddgs", side_effect=fake_search_ddgs) as mock_ddgs, \
			 patch.object(doc, "_search_wikipedia", return_value=[]) as mock_wiki:
			results = doc._search_web_results("Apple AAPL stock earnings 10-K")

		mock_ddgs.assert_called_once()
		mock_wiki.assert_not_called()

	def test_search_web_results_auto_uses_wikipedia_for_general(self):
		doc = _make_doc()

		with patch.object(doc, "_search_ddgs", return_value=[]) as mock_ddgs, \
			 patch.object(doc, "_search_wikipedia", return_value=[]) as mock_wiki:
			doc._search_web_results("history of the Roman Empire")

		mock_ddgs.assert_called_once()
		mock_wiki.assert_called_once()

	def test_search_web_results_deduplicates(self):
		doc = _make_doc()
		dup_results = [
			{"url": "https://dup.com/page", "title": "Dup", "snippet": "x", "source": "ddgs"},
			{"url": "https://dup.com/page", "title": "Dup 2", "snippet": "x", "source": "ddgs"},
			{"url": "https://other.com/page", "title": "Other", "snippet": "y", "source": "ddgs"},
		]
		with patch.object(doc, "_search_ddgs", return_value=dup_results):
			results = doc._search_web_results("query", num_results=10, providers=["ddgs"])

		urls = [r["url"] for r in results]
		self.assertEqual(len(urls), len(set(urls)))

	# ------------------------------------------------------------------
	# _search_financial_sources routing
	# ------------------------------------------------------------------

	def test_search_financial_sources_auto_calls_all_three_sources(self):
		doc = _make_doc()
		with patch.object(doc, "_search_edgar", return_value=[]) as mock_edgar, \
			 patch.object(doc, "_search_ddgs", return_value=[]) as mock_ddgs:
			doc._search_financial_sources("Apple revenue", source="auto")

		mock_edgar.assert_called_once()
		# _search_ddgs called twice: yahoo_finance and financial_news
		self.assertEqual(mock_ddgs.call_count, 2)

	def test_search_financial_sources_sec_edgar_only(self):
		doc = _make_doc()
		with patch.object(doc, "_search_edgar", return_value=[]) as mock_edgar, \
			 patch.object(doc, "_search_ddgs", return_value=[]) as mock_ddgs:
			doc._search_financial_sources("10-K", source="sec_edgar")

		mock_edgar.assert_called_once()
		mock_ddgs.assert_not_called()

	def test_search_financial_sources_respects_max_results(self):
		doc = _make_doc()
		many = [{"url": f"https://sec.gov/{i}", "title": str(i), "snippet": "s", "source": "sec_edgar"} for i in range(20)]
		with patch.object(doc, "_search_edgar", return_value=many), \
			 patch.object(doc, "_search_ddgs", return_value=[]):
			results = doc._search_financial_sources("Apple", max_results=3)

		self.assertLessEqual(len(results), 3)

	# ------------------------------------------------------------------
	# FINANCIAL_QUERY_KEYWORDS constant sanity
	# ------------------------------------------------------------------

	def test_financial_keywords_non_empty_frozenset(self):
		self.assertIsInstance(FINANCIAL_QUERY_KEYWORDS, frozenset)
		self.assertGreater(len(FINANCIAL_QUERY_KEYWORDS), 0)

	def test_financial_keywords_include_core_terms(self):
		for term in ("stock", "earnings", "10-k", "sec", "edgar", "dividend"):
			self.assertIn(term, FINANCIAL_QUERY_KEYWORDS)


class TestCFChatMessageTokenAndThinkingModes(FrappeTestCase):
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


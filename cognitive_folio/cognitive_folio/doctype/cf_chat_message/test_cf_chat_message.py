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


# DSML separator character used by deepseek-reasoner
_SEP = "\uff5c"


def _dsml(tag):
	return f"<{_SEP}DSML{_SEP}{tag}>"


def _dsml_close(tag):
	return f"</{_SEP}DSML{_SEP}{tag}>"


def _make_dsml_content(tool_name, params):
	"""Build a minimal DSML function-call string."""
	lines = [_dsml("functioncalls"), _dsml(f'invoke name="{tool_name}"')]
	for pname, pvalue in params.items():
		lines.append(_dsml(f'parameter name="{pname}" string="true"') + str(pvalue))
	lines.append(_dsml_close("invoke"))
	lines.append(_dsml_close("functioncalls"))
	return "\n".join(lines)


class TestCFChatMessageDSML(FrappeTestCase):
	"""Unit tests for DeepSeek-Reasoner DSML function-call parsing helpers."""

	# ------------------------------------------------------------------
	# _has_dsml_tool_calls
	# ------------------------------------------------------------------

	def test_has_dsml_detects_markup(self):
		doc = _make_doc()
		content = _make_dsml_content("fetch_url_content", {"url": "https://example.com"})
		self.assertTrue(doc._has_dsml_tool_calls(content))

	def test_has_dsml_returns_false_for_plain_text(self):
		doc = _make_doc()
		self.assertFalse(doc._has_dsml_tool_calls("Just a normal response."))

	def test_has_dsml_returns_false_for_empty_string(self):
		doc = _make_doc()
		self.assertFalse(doc._has_dsml_tool_calls(""))

	def test_has_dsml_returns_false_for_none(self):
		doc = _make_doc()
		self.assertFalse(doc._has_dsml_tool_calls(None))

	# ------------------------------------------------------------------
	# _resolve_dsml_tool_name
	# ------------------------------------------------------------------

	def test_resolve_tool_name_exact(self):
		doc = _make_doc()
		self.assertEqual(doc._resolve_dsml_tool_name("fetch_url_content"), "fetch_url_content")
		self.assertEqual(doc._resolve_dsml_tool_name("web_search"), "web_search")
		self.assertEqual(doc._resolve_dsml_tool_name("search_financial"), "search_financial")

	def test_resolve_tool_name_no_underscores(self):
		doc = _make_doc()
		# deepseek-reasoner drops underscores/casing
		self.assertEqual(doc._resolve_dsml_tool_name("fetchurlcontent"), "fetch_url_content")
		self.assertEqual(doc._resolve_dsml_tool_name("websearch"), "web_search")
		self.assertEqual(doc._resolve_dsml_tool_name("getsecuritysnapshot"), "get_security_snapshot")

	def test_resolve_tool_name_mixed_case(self):
		doc = _make_doc()
		self.assertEqual(doc._resolve_dsml_tool_name("FetchUrlContent"), "fetch_url_content")
		self.assertEqual(doc._resolve_dsml_tool_name("WebSearch"), "web_search")

	def test_resolve_tool_name_unknown_returns_none(self):
		doc = _make_doc()
		self.assertIsNone(doc._resolve_dsml_tool_name("totally_unknown_tool"))
		self.assertIsNone(doc._resolve_dsml_tool_name(""))

	# ------------------------------------------------------------------
	# _resolve_dsml_param_name
	# ------------------------------------------------------------------

	def test_resolve_param_name_exact(self):
		doc = _make_doc()
		self.assertEqual(doc._resolve_dsml_param_name("fetch_url_content", "url"), "url")
		self.assertEqual(doc._resolve_dsml_param_name("fetch_url_content", "max_chars"), "max_chars")

	def test_resolve_param_name_no_underscores(self):
		doc = _make_doc()
		self.assertEqual(doc._resolve_dsml_param_name("fetch_url_content", "maxchars"), "max_chars")
		self.assertEqual(doc._resolve_dsml_param_name("web_search", "maxresults"), "max_results")
		self.assertEqual(doc._resolve_dsml_param_name("web_search", "domainfilter"), "domain_filter")

	def test_resolve_param_name_unknown_returns_raw(self):
		doc = _make_doc()
		result = doc._resolve_dsml_param_name("fetch_url_content", "totally_unknown_param")
		self.assertEqual(result, "totally_unknown_param")

	# ------------------------------------------------------------------
	# _parse_dsml_tool_calls
	# ------------------------------------------------------------------

	def test_parse_single_tool_call(self):
		doc = _make_doc()
		content = _make_dsml_content("fetch_url_content", {"url": "https://example.com", "maxchars": "5000"})
		calls = doc._parse_dsml_tool_calls(content)
		self.assertEqual(len(calls), 1)
		tc = calls[0]
		self.assertEqual(tc.function.name, "fetch_url_content")
		import json
		args = json.loads(tc.function.arguments)
		self.assertEqual(args.get("url"), "https://example.com")
		self.assertEqual(args.get("max_chars"), "5000")

	def test_parse_normalises_tool_name(self):
		doc = _make_doc()
		content = _make_dsml_content("fetchurlcontent", {"url": "https://sec.gov"})
		calls = doc._parse_dsml_tool_calls(content)
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0].function.name, "fetch_url_content")

	def test_parse_skips_unknown_tools(self):
		doc = _make_doc()
		content = _make_dsml_content("totally_unknown_tool", {"arg": "val"})
		calls = doc._parse_dsml_tool_calls(content)
		self.assertEqual(calls, [])

	def test_parse_web_search_call(self):
		doc = _make_doc()
		content = _make_dsml_content("websearch", {"query": "USA Iran war 2026"})
		calls = doc._parse_dsml_tool_calls(content)
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0].function.name, "web_search")
		import json
		args = json.loads(calls[0].function.arguments)
		self.assertEqual(args.get("query"), "USA Iran war 2026")

	def test_parse_assigns_unique_call_ids(self):
		doc = _make_doc()
		content = (
			_make_dsml_content("websearch", {"query": "test 1"})
			+ "\n"
			+ _make_dsml_content("fetchurlcontent", {"url": "https://a.com"})
		)
		calls = doc._parse_dsml_tool_calls(content)
		self.assertGreaterEqual(len(calls), 1)
		ids = [c.id for c in calls]
		self.assertEqual(len(ids), len(set(ids)), "call IDs must be unique")

	def test_parse_returns_empty_for_plain_text(self):
		doc = _make_doc()
		self.assertEqual(doc._parse_dsml_tool_calls("Just a normal response."), [])

	def test_parse_dsml_tool_call_has_id(self):
		doc = _make_doc()
		content = _make_dsml_content("websearch", {"query": "test"})
		calls = doc._parse_dsml_tool_calls(content)
		self.assertIsNotNone(calls[0].id)
		self.assertTrue(calls[0].id.startswith("dsml_"))

	# ------------------------------------------------------------------
	# _strip_dsml_markup
	# ------------------------------------------------------------------

	def test_strip_removes_markup(self):
		doc = _make_doc()
		content = "Some prose.\n" + _make_dsml_content("websearch", {"query": "test"})
		stripped = doc._strip_dsml_markup(content)
		self.assertNotIn(_SEP, stripped)
		self.assertIn("Some prose.", stripped)

	def test_strip_returns_unchanged_for_plain_text(self):
		doc = _make_doc()
		text = "Normal response without DSML."
		self.assertEqual(doc._strip_dsml_markup(text), text)

	def test_strip_handles_content_before_and_after(self):
		doc = _make_doc()
		content = "Before.\n" + _make_dsml_content("websearch", {"query": "q"}) + "\nAfter."
		stripped = doc._strip_dsml_markup(content)
		self.assertNotIn(_SEP, stripped)

import unittest
from unittest.mock import MagicMock

from cognitive_folio.cognitive_folio.services.web_search_service import WebSearchService


class TestWebSearchServiceProviderRouting(unittest.TestCase):
    def _make_service(self):
        chat_message = MagicMock()
        chat_message.prompt = "find latest market updates"
        service = WebSearchService(chat_message)
        service._search_provider_config = {
            "general_chain": ["ddgs", "wikipedia"],
            "financial_chain": ["ddgs", "sec_edgar", "financial_news", "yahoo_finance"],
            "financial_domains": [],
            "max_results": 5,
            "serpapi_enabled": False,
            "serpapi_api_key": "",
            "serpapi_engine": "google",
            "sec_realtime_enabled": True,
            "sec_user_agent": "CognitiveFolio/1.0 test@example.com",
            "provider_timeout_seconds": 15,
            "query_refiner_enabled": False,
            "query_refiner_llm_enabled": False,
            "result_reranker_enabled": False,
            "result_reranker_top_k": 8,
            "freshness_weighting_enabled": True,
            "freshness_half_life_days": 21,
            "cross_source_verifier_enabled": True,
            "cross_source_min_sources": 2,
            "cross_source_contradiction_penalty": 0.25,
            "cross_source_confidence_boost": 0.1,
            "domain_authority_enabled": True,
            "domain_authority_default_weight": 0.2,
            "domain_authority_weights": {},
            "session_tracker_enabled": True,
            "session_max_entries": 25,
            "session_context_max_items": 3,
            "session_context_max_chars": 180,
            "session_followup_expand_enabled": True,
            "semantic_search_enabled": False,
            "semantic_embedding_dims": 96,
            "semantic_score_weight": 0.6,
            "trend_detector_enabled": False,
            "trend_min_frequency": 2,
            "trend_score_weight": 0.4,
            "personalized_search_enabled": False,
            "personalized_score_weight": 0.35,
            "personalized_history_items": 5,
            "preferred_sources": [],
            "preferred_domains": [],
        }
        service._apply_registry_chains(service._search_provider_config)
        service.extract_search_query = lambda prompt_text=None: (prompt_text or chat_message.prompt)
        return service

    def test_web_search_fallback_to_next_provider(self):
        service = self._make_service()
        service.provider_registry.set_chain("general", ["ddgs", "wikipedia"])
        service.provider_registry.register("ddgs", lambda **_: [])
        service.provider_registry.register(
            "wikipedia",
            lambda **_: [
                {
                    "title": "Market Overview",
                    "url": "https://example.com/market",
                    "snippet": "Market update",
                    "source": "wikipedia",
                }
            ],
        )

        results = service.search_web_results("market overview", num_results=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "wikipedia")

    def test_financial_search_respects_explicit_source_hint(self):
        service = self._make_service()
        service.provider_registry.register(
            "sec_edgar",
            lambda **_: [
                {
                    "title": "SEC Filing",
                    "url": "https://sec.example/filing",
                    "snippet": "10-K filing",
                    "source": "sec_edgar",
                }
            ],
        )

        results = service.search_financial_sources(
            query="10-k filing",
            ticker="AAPL",
            source="sec_edgar",
            max_results=3,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "sec_edgar")

    def test_web_search_supports_explicit_provider_list(self):
        service = self._make_service()
        service.provider_registry.register(
            "wikipedia",
            lambda **_: [
                {
                    "title": "Topic",
                    "url": "https://example.com/topic",
                    "snippet": "Topic snippet",
                    "source": "wikipedia",
                }
            ],
        )

        results = service.search_web_results(
            "topic",
            num_results=2,
            providers=["wikipedia"],
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "wikipedia")

    def test_web_search_supports_serpapi_when_enabled(self):
        service = self._make_service()
        service._search_provider_config = {
            "general_chain": ["serpapi"],
            "financial_chain": ["serpapi", "sec_edgar"],
            "serpapi_enabled": True,
            "serpapi_api_key": "demo-key",
            "serpapi_engine": "google",
            "provider_timeout_seconds": 10,
            "financial_domains": [],
            "max_results": 5,
        }
        service._apply_registry_chains(service._search_provider_config)
        service.search_serpapi = lambda **_: [
            {
                "title": "SerpAPI Result",
                "url": "https://example.com/serpapi",
                "snippet": "SerpAPI snippet",
                "source": "serpapi",
            }
        ]

        results = service.search_web_results("macro outlook", num_results=2, providers=["serpapi"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "serpapi")

    def test_financial_search_merges_sec_realtime_and_search_index(self):
        service = self._make_service()
        service._search_provider_config["result_reranker_enabled"] = False
        service.provider_registry.set_chain("financial", ["sec_edgar"])

        service.search_edgar_realtime = lambda **_: [
            {
                "title": "Realtime Filing",
                "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/aapl-20251231x10k.htm",
                "snippet": "Realtime filing",
                "source": "sec_edgar",
            }
        ]
        service.search_edgar = lambda **_: [
            {
                "title": "Search Filing",
                "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000011/aapl-20260331x10q.htm",
                "snippet": "Search filing",
                "source": "sec_edgar",
            }
        ]

        results = service.search_financial_sources(
            query="latest filings",
            ticker="AAPL",
            source="sec_edgar",
            max_results=5,
        )

        urls = {item.get("url") for item in results}
        self.assertIn("https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/aapl-20251231x10k.htm", urls)
        self.assertIn("https://www.sec.gov/Archives/edgar/data/320193/000032019326000011/aapl-20260331x10q.htm", urls)

    def test_web_search_uses_query_refiner(self):
        service = self._make_service()
        service._search_provider_config["query_refiner_enabled"] = True
        service._search_provider_config["session_followup_expand_enabled"] = False
        service._search_provider_config["result_reranker_enabled"] = False
        captured_queries = []

        service.query_refiner.refine = lambda **_: "refined topic"
        service.provider_registry.register(
            "ddgs",
            lambda **kwargs: captured_queries.append(kwargs.get("query")) or [
                {
                    "title": "Topic",
                    "url": "https://example.com/topic",
                    "snippet": "Topic snippet",
                    "source": "ddgs",
                }
            ],
        )
        service.provider_registry.set_chain("general", ["ddgs"])

        service.search_web_results("original query", num_results=1)

        self.assertEqual(captured_queries, ["refined topic"])

    def test_web_search_expands_follow_up_with_session_context(self):
        service = self._make_service()
        service._search_provider_config["query_refiner_enabled"] = False
        service._search_provider_config["session_followup_expand_enabled"] = True
        service._search_provider_config["result_reranker_enabled"] = False
        captured_queries = []

        service.search_session_tracker.expand_follow_up_query = lambda **_: "what about it about tsla earnings"
        service.provider_registry.set_chain("general", ["ddgs"])
        service.provider_registry.register(
            "ddgs",
            lambda **kwargs: captured_queries.append(kwargs.get("query")) or [
                {
                    "title": "Topic",
                    "url": "https://example.com/topic",
                    "snippet": "Topic snippet",
                    "source": "ddgs",
                }
            ],
        )

        service.search_web_results("what about it", num_results=1)

        self.assertEqual(captured_queries, ["what about it about tsla earnings"])

    def test_web_search_records_session_entry(self):
        service = self._make_service()
        service._search_provider_config["query_refiner_enabled"] = False
        service._search_provider_config["result_reranker_enabled"] = False
        calls = []

        service.search_session_tracker.record_search = lambda **kwargs: calls.append(kwargs) or {"stored": True}
        service.provider_registry.set_chain("general", ["ddgs"])
        service.provider_registry.register(
            "ddgs",
            lambda **_: [
                {
                    "title": "Topic",
                    "url": "https://example.com/topic",
                    "snippet": "Topic snippet",
                    "source": "ddgs",
                }
            ],
        )

        service.search_web_results("topic", num_results=1)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["query"], "topic")

    def test_web_search_applies_reranker(self):
        service = self._make_service()
        service._search_provider_config["query_refiner_enabled"] = False
        service._search_provider_config["result_reranker_enabled"] = True
        service._search_provider_config["result_reranker_top_k"] = 5
        service._search_provider_config["domain_authority_enabled"] = True
        service._search_provider_config["domain_authority_default_weight"] = 0.1
        service._search_provider_config["domain_authority_weights"] = {"example.com": 0.9}
        service._search_provider_config["cross_source_contradiction_penalty"] = 0.4
        service._search_provider_config["cross_source_confidence_boost"] = 0.2
        service._search_provider_config["semantic_search_enabled"] = True
        service._search_provider_config["semantic_embedding_dims"] = 64
        service._search_provider_config["semantic_score_weight"] = 0.8
        service._search_provider_config["trend_detector_enabled"] = True
        service._search_provider_config["trend_min_frequency"] = 3
        service._search_provider_config["trend_score_weight"] = 0.5
        service._search_provider_config["personalized_search_enabled"] = True
        service._search_provider_config["personalized_score_weight"] = 0.45
        service._search_provider_config["personalized_history_items"] = 3
        service._search_provider_config["preferred_sources"] = ["wikipedia"]
        service._search_provider_config["preferred_domains"] = ["pref.example"]
        service.provider_registry.set_chain("general", ["ddgs", "wikipedia"])

        service.search_session_tracker.get_recent_history = lambda **_: [
            {
                "providers": ["financial_news"],
                "top_urls": ["https://history.example/report"],
            }
        ]

        service.provider_registry.register(
            "ddgs",
            lambda **_: [{"title": "A", "url": "https://example.com/a", "snippet": "A", "source": "ddgs"}],
        )
        service.provider_registry.register(
            "wikipedia",
            lambda **_: [{"title": "B", "url": "https://example.com/b", "snippet": "B", "source": "wikipedia"}],
        )
        captured = {}

        def fake_rerank(**kwargs):
            captured.update(kwargs)
            return [kwargs["results"][1], kwargs["results"][0]]

        service.result_reranker.rerank = fake_rerank

        results = service.search_web_results("topic", num_results=2)

        self.assertEqual(results[0]["url"], "https://example.com/b")
        self.assertTrue(captured["options"]["domain_authority_enabled"])
        self.assertEqual(captured["options"]["domain_authority_default_weight"], 0.1)
        self.assertEqual(captured["options"]["domain_authority_weights"], {"example.com": 0.9})
        self.assertEqual(captured["options"]["cross_source_contradiction_penalty"], 0.4)
        self.assertEqual(captured["options"]["cross_source_confidence_boost"], 0.2)
        self.assertTrue(captured["options"]["semantic_search_enabled"])
        self.assertEqual(captured["options"]["semantic_embedding_dims"], 64)
        self.assertEqual(captured["options"]["semantic_score_weight"], 0.8)
        self.assertTrue(captured["options"]["trend_detector_enabled"])
        self.assertEqual(captured["options"]["trend_min_frequency"], 3)
        self.assertEqual(captured["options"]["trend_score_weight"], 0.5)
        self.assertTrue(captured["options"]["personalized_search_enabled"])
        self.assertEqual(captured["options"]["personalized_score_weight"], 0.45)
        self.assertIn("wikipedia", captured["options"]["personalization_context"]["preferred_sources"])
        self.assertIn("financial_news", captured["options"]["personalization_context"]["preferred_sources"])
        self.assertIn("pref.example", captured["options"]["personalization_context"]["preferred_domains"])
        self.assertIn("history.example", captured["options"]["personalization_context"]["preferred_domains"])

    def test_web_search_uses_result_cache(self):
        service = self._make_service()
        service._search_provider_config["query_refiner_enabled"] = False
        service._search_provider_config["result_reranker_enabled"] = False
        service.provider_registry.set_chain("general", ["ddgs"])

        calls = []

        service.provider_registry.register(
            "ddgs",
            lambda **_: calls.append("called") or [
                {
                    "title": "Cached Topic",
                    "url": "https://example.com/cached",
                    "snippet": "Cached snippet",
                    "source": "ddgs",
                }
            ],
        )

        first = service.search_web_results("cached topic", num_results=1)
        second = service.search_web_results("cached topic", num_results=1)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(calls, ["called"])

    def test_web_search_skips_provider_when_circuit_breaker_open(self):
        service = self._make_service()
        service._search_provider_config["query_refiner_enabled"] = False
        service._search_provider_config["result_reranker_enabled"] = False
        service.provider_registry.set_chain("general", ["ddgs", "wikipedia"])

        service.circuit_breaker.allow_request = lambda provider: provider != "ddgs"
        service.rate_limiter.allow = lambda provider: True
        service.provider_registry.register("ddgs", lambda **_: [{"title": "D", "url": "https://example.com/d", "snippet": "D", "source": "ddgs"}])
        service.provider_registry.register("wikipedia", lambda **_: [{"title": "W", "url": "https://example.com/w", "snippet": "W", "source": "wikipedia"}])

        results = service.search_web_results("topic", num_results=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "wikipedia")

    def test_web_search_includes_weather_fallback_result(self):
        service = self._make_service()
        service._search_provider_config["query_refiner_enabled"] = False
        service._search_provider_config["result_reranker_enabled"] = False
        service.provider_registry.set_chain("general", ["ddgs"])
        service.provider_registry.register("ddgs", lambda **_: [])

        service._search_weather_now = lambda _query: [
            {
                "title": "Current weather in Larnaka Cyprus",
                "url": "https://wttr.in/Larnaka+Cyprus",
                "snippet": "Temperature: 21C. Conditions: Clear.",
                "source": "wttr.in",
            }
        ]

        results = service.search_web_results("What is the weather now in Larnaka Cyprus?", num_results=3)

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "wttr.in")

import unittest

from cognitive_folio.cognitive_folio.services.performance import (
    CircuitBreakerManager,
    PredictivePrefetching,
    RateLimiter,
    SearchResultCache,
    ToolResultCache,
)


class TestPhase4PerformanceServices(unittest.TestCase):
    def test_search_result_cache_round_trip(self):
        cache = SearchResultCache(
            config={
                "search_cache_enabled": True,
                "search_cache_ttl_general_seconds": 60,
                "search_cache_ttl_financial_seconds": 30,
                "search_cache_ttl_realtime_seconds": 15,
            }
        )
        payload = {"query": "market overview", "query_type": "general"}
        expected = [{"title": "Overview", "url": "https://example.com/overview"}]

        cache.set("search_web_results", payload, expected, query_type="general")
        cached = cache.get("search_web_results", payload)

        self.assertEqual(cached, expected)

    def test_tool_result_cache_respects_allowed_tools(self):
        cache = ToolResultCache(config={"tool_result_cache_enabled": True, "tool_result_cache_ttl_seconds": 120})
        cached_result = {"ok": True, "result": {"value": 1}}

        cache.set("web_search", "{}", "chat-1", None, None, True, cached_result)
        hit = cache.get("web_search", "{}", "chat-1", None, None, True)

        self.assertEqual(hit, cached_result)
        self.assertIsNone(cache.get("non_cacheable_tool", "{}", "chat-1", None, None, True))

    def test_circuit_breaker_opens_after_threshold(self):
        breaker = CircuitBreakerManager(
            config={
                "search_circuit_breaker_enabled": True,
                "search_circuit_breaker_failure_threshold": 2,
                "search_circuit_breaker_recovery_seconds": 60,
                "search_circuit_breaker_half_open_calls": 1,
            }
        )

        self.assertTrue(breaker.allow_request("ddgs"))
        breaker.record_failure("ddgs")
        self.assertTrue(breaker.allow_request("ddgs"))
        breaker.record_failure("ddgs")

        self.assertFalse(breaker.allow_request("ddgs"))

    def test_rate_limiter_blocks_after_capacity_exhausted(self):
        limiter = RateLimiter(
            config={
                "search_rate_limiter_enabled": True,
                "search_rate_limit_per_provider_per_minute": 1,
            }
        )

        self.assertTrue(limiter.allow("ddgs"))
        self.assertFalse(limiter.allow("ddgs"))

    def test_predictive_prefetching_predicts_queries(self):
        prefetch = PredictivePrefetching(
            config={
                "search_prefetch_enabled": True,
                "search_prefetch_max_queries": 2,
            }
        )

        predicted = prefetch.predict_queries(query="AAPL guidance", query_type="financial", ticker="AAPL")

        self.assertGreaterEqual(len(predicted), 1)
        self.assertLessEqual(len(predicted), 2)


if __name__ == "__main__":
    unittest.main()

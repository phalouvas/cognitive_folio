import unittest
from datetime import datetime, timezone

from cognitive_folio.cognitive_folio.services.search import ResultReranker


class TestResultReranker(unittest.TestCase):
    def test_rerank_prioritizes_lexical_relevance(self):
        reranker = ResultReranker()

        results = [
            {"title": "Macro digest", "snippet": "general market notes", "url": "https://example.com/a", "source": "ddgs"},
            {"title": "Fed inflation outlook", "snippet": "inflation and policy update", "url": "https://example.com/b", "source": "ddgs"},
        ]

        ranked = reranker.rerank("fed inflation", results, query_type="general")

        self.assertEqual(ranked[0]["url"], "https://example.com/b")

    def test_rerank_prioritizes_authoritative_financial_source(self):
        reranker = ResultReranker()

        results = [
            {"title": "Analysis", "snippet": "earnings update", "url": "https://randomblog.example/tsla", "source": "ddgs"},
            {"title": "Filing", "snippet": "10-K annual filing", "url": "https://www.sec.gov/Archives/x", "source": "sec_edgar"},
        ]

        ranked = reranker.rerank("10-k tsla", results, query_type="financial", ticker="TSLA")

        self.assertEqual(ranked[0]["source"], "sec_edgar")

    def test_rerank_honors_top_k(self):
        reranker = ResultReranker()

        results = [
            {"title": f"Result {idx}", "snippet": "snippet", "url": f"https://example.com/{idx}", "source": "ddgs"}
            for idx in range(10)
        ]

        ranked = reranker.rerank("query", results, query_type="general", top_k=3)

        self.assertEqual(len(ranked), 3)

    def test_rerank_prefers_fresher_result_when_enabled(self):
        reranker = ResultReranker()

        results = [
            {
                "title": "Fed policy outlook",
                "snippet": "inflation trajectory and rate guidance",
                "url": "https://example.com/old",
                "source": "ddgs",
                "date": "2024-01-01",
            },
            {
                "title": "Fed policy outlook",
                "snippet": "inflation trajectory and rate guidance",
                "url": "https://example.com/new",
                "source": "ddgs",
                "date": "2026-03-01",
            },
        ]

        ranked = reranker.rerank(
            "fed inflation",
            results,
            query_type="general",
            options={
                "freshness_enabled": True,
                "freshness_half_life_days": 30,
                "cross_source_enabled": False,
                "now_utc": datetime(2026, 3, 7, tzinfo=timezone.utc),
            },
        )

        self.assertEqual(ranked[0]["url"], "https://example.com/new")

    def test_rerank_boosts_cross_source_corroboration(self):
        reranker = ResultReranker()

        results = [
            {
                "title": "TSLA earnings beat expectations",
                "snippet": "TSLA revenue and margin beat analyst consensus",
                "url": "https://reuters.com/markets/tsla-earnings",
                "source": "financial_news",
            },
            {
                "title": "Analysts note TSLA earnings beat expectations",
                "snippet": "revenue beat and margin expansion",
                "url": "https://www.wsj.com/markets/tsla-earnings",
                "source": "financial_news",
            },
            {
                "title": "TSLA factory hiring plans",
                "snippet": "new hiring cycle announced",
                "url": "https://example.com/tsla-hiring",
                "source": "ddgs",
            },
        ]

        ranked = reranker.rerank(
            "tsla earnings beat",
            results,
            query_type="financial",
            options={
                "freshness_enabled": False,
                "cross_source_enabled": True,
                "cross_source_min_sources": 1,
            },
        )

        self.assertIn(ranked[0]["url"], {
            "https://reuters.com/markets/tsla-earnings",
            "https://www.wsj.com/markets/tsla-earnings",
        })

    def test_rerank_respects_domain_authority_toggle(self):
        reranker = ResultReranker()

        results = [
            {"title": "Filing", "snippet": "10-K", "url": "https://www.sec.gov/Archives/x", "source": "ddgs"},
            {"title": "Filing", "snippet": "10-K", "url": "https://random.example/x", "source": "ddgs"},
        ]

        ranked = reranker.rerank(
            "10-k filing",
            results,
            query_type="financial",
            options={
                "domain_authority_enabled": False,
                "freshness_enabled": False,
                "cross_source_enabled": False,
            },
        )

        self.assertEqual(ranked[0]["url"], "https://www.sec.gov/Archives/x")

    def test_rerank_uses_custom_domain_authority_weights(self):
        reranker = ResultReranker()

        results = [
            {"title": "Coverage", "snippet": "earnings report", "url": "https://alpha.example/report", "source": "ddgs"},
            {"title": "Coverage", "snippet": "earnings report", "url": "https://beta.example/report", "source": "ddgs"},
        ]

        ranked = reranker.rerank(
            "earnings report",
            results,
            query_type="general",
            options={
                "freshness_enabled": False,
                "cross_source_enabled": False,
                "domain_authority_enabled": True,
                "domain_authority_weights": {"beta.example": 1.1, "alpha.example": 0.2},
                "domain_authority_default_weight": 0.0,
            },
        )

        self.assertEqual(ranked[0]["url"], "https://beta.example/report")

    def test_rerank_cross_source_penalty_changes_order(self):
        reranker = ResultReranker()

        results = [
            {
                "title": "TSLA earnings beat expectations",
                "snippet": "strong growth and margin expansion",
                "url": "https://reuters.com/markets/tsla",
                "source": "financial_news",
            },
            {
                "title": "TSLA missed earnings expectations",
                "snippet": "weak growth and downgrade risk",
                "url": "https://www.wsj.com/markets/tsla",
                "source": "financial_news",
            },
            {
                "title": "TSLA production update",
                "snippet": "factory expansion progress",
                "url": "https://example.com/tsla-prod",
                "source": "ddgs",
            },
        ]

        ranked = reranker.rerank(
            "tsla earnings",
            results,
            query_type="financial",
            options={
                "freshness_enabled": False,
                "domain_authority_enabled": False,
                "cross_source_enabled": True,
                "cross_source_min_sources": 1,
                "cross_source_contradiction_penalty": 0.5,
                "cross_source_confidence_boost": 0.1,
            },
        )

        self.assertEqual(ranked[0]["url"], "https://reuters.com/markets/tsla")

    def test_rerank_applies_semantic_search_boost(self):
        reranker = ResultReranker()

        results = [
            {
                "title": "Bond yield curve inversion",
                "snippet": "fixed income term structure discussion",
                "url": "https://example.com/bonds",
                "source": "ddgs",
            },
            {
                "title": "TSLA earnings growth outlook",
                "snippet": "Tesla margin expansion and earnings momentum",
                "url": "https://example.com/tsla-earnings",
                "source": "ddgs",
            },
        ]

        ranked = reranker.rerank(
            "tsla earnings growth",
            results,
            query_type="financial",
            options={
                "freshness_enabled": False,
                "cross_source_enabled": False,
                "domain_authority_enabled": False,
                "semantic_search_enabled": True,
                "semantic_embedding_dims": 64,
                "semantic_score_weight": 0.9,
            },
        )

        self.assertEqual(ranked[0]["url"], "https://example.com/tsla-earnings")

    def test_rerank_applies_trend_detector_boost(self):
        reranker = ResultReranker()

        results = [
            {
                "title": "TSLA earnings trend strengthens",
                "snippet": "earnings momentum and recurring upside",
                "url": "https://example.com/tsla-trend",
                "source": "ddgs",
            },
            {
                "title": "Bond market roundup",
                "snippet": "yield curve observations",
                "url": "https://example.com/bonds",
                "source": "ddgs",
            },
            {
                "title": "TSLA earnings update",
                "snippet": "earnings trajectory and growth",
                "url": "https://example.com/tsla-update",
                "source": "ddgs",
            },
        ]

        ranked = reranker.rerank(
            "tsla earnings",
            results,
            query_type="financial",
            options={
                "freshness_enabled": False,
                "cross_source_enabled": False,
                "domain_authority_enabled": False,
                "semantic_search_enabled": False,
                "trend_detector_enabled": True,
                "trend_min_frequency": 2,
                "trend_score_weight": 0.6,
            },
        )

        self.assertEqual(ranked[0]["url"], "https://example.com/tsla-trend")

    def test_rerank_applies_personalized_search_boost(self):
        reranker = ResultReranker()

        results = [
            {
                "title": "Macro outlook",
                "snippet": "global rates",
                "url": "https://example.com/macro",
                "source": "ddgs",
            },
            {
                "title": "TSLA update",
                "snippet": "Tesla demand outlook",
                "url": "https://www.reuters.com/markets/tsla",
                "source": "financial_news",
            },
        ]

        ranked = reranker.rerank(
            "latest outlook",
            results,
            query_type="financial",
            options={
                "freshness_enabled": False,
                "cross_source_enabled": False,
                "domain_authority_enabled": False,
                "semantic_search_enabled": False,
                "trend_detector_enabled": False,
                "personalized_search_enabled": True,
                "personalized_score_weight": 0.9,
                "personalization_context": {
                    "preferred_sources": ["financial_news"],
                    "preferred_domains": ["reuters.com"],
                    "preferred_tickers": ["tsla"],
                    "preferred_query_type": "financial",
                },
            },
        )

        self.assertEqual(ranked[0]["url"], "https://www.reuters.com/markets/tsla")

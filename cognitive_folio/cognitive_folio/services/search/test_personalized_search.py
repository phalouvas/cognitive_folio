import unittest

from cognitive_folio.cognitive_folio.services.search import PersonalizedSearch


class TestPersonalizedSearch(unittest.TestCase):
    def test_scores_source_domain_and_ticker_preference(self):
        scorer = PersonalizedSearch()

        result = {
            "title": "TSLA earnings outlook",
            "snippet": "Tesla margin expansion",
            "url": "https://www.reuters.com/markets/tsla",
            "source": "financial_news",
        }
        context = {
            "preferred_sources": ["financial_news"],
            "preferred_domains": ["reuters.com"],
            "preferred_tickers": ["tsla"],
            "preferred_query_type": "financial",
            "query_type": "financial",
        }

        score = scorer.score(result, context=context, weight=0.5)

        self.assertGreater(score, 0.3)

    def test_zero_when_no_preferences_match(self):
        scorer = PersonalizedSearch()

        result = {
            "title": "Bond market overview",
            "snippet": "yield curve movements",
            "url": "https://example.com/bonds",
            "source": "ddgs",
        }
        context = {
            "preferred_sources": ["sec_edgar"],
            "preferred_domains": ["sec.gov"],
            "preferred_tickers": ["aapl"],
            "preferred_query_type": "financial",
            "query_type": "general",
        }

        score = scorer.score(result, context=context, weight=0.6)

        self.assertEqual(score, 0.0)

    def test_weight_controls_magnitude(self):
        scorer = PersonalizedSearch()

        result = {
            "title": "MSFT update",
            "snippet": "MSFT guidance",
            "url": "https://example.com/msft",
            "source": "ddgs",
        }
        context = {
            "preferred_sources": ["ddgs"],
            "preferred_domains": ["example.com"],
            "preferred_tickers": ["msft"],
            "preferred_query_type": "general",
            "query_type": "general",
        }

        low = scorer.score(result, context=context, weight=0.1)
        high = scorer.score(result, context=context, weight=0.9)

        self.assertGreater(high, low)

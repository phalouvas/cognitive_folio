import unittest

from cognitive_folio.cognitive_folio.services.search import SemanticSearch


class TestSemanticSearch(unittest.TestCase):
    def test_score_prefers_semantically_related_result(self):
        scorer = SemanticSearch()

        related = {
            "title": "TSLA earnings and margin expansion",
            "snippet": "Tesla reported strong earnings growth",
        }
        unrelated = {
            "title": "Bond ladder construction",
            "snippet": "How to build a fixed income ladder",
        }

        related_score = scorer.score("tsla earnings growth", related, dims=64, weight=0.7)
        unrelated_score = scorer.score("tsla earnings growth", unrelated, dims=64, weight=0.7)

        self.assertGreater(related_score, unrelated_score)

    def test_score_respects_weight(self):
        scorer = SemanticSearch()
        result = {"title": "Fed policy outlook", "snippet": "Inflation and rates update"}

        low = scorer.score("fed inflation", result, dims=64, weight=0.1)
        high = scorer.score("fed inflation", result, dims=64, weight=0.9)

        self.assertGreater(high, low)

    def test_score_handles_empty_inputs(self):
        scorer = SemanticSearch()

        self.assertEqual(scorer.score("", {"title": "x", "snippet": "y"}), 0.0)
        self.assertEqual(scorer.score("query", {}), 0.0)

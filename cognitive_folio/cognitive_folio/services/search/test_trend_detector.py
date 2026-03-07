import unittest

from cognitive_folio.cognitive_folio.services.search import TrendDetector


class TestTrendDetector(unittest.TestCase):
    def test_extract_trends_with_frequency_threshold(self):
        detector = TrendDetector()

        results = [
            {"title": "TSLA earnings beat", "snippet": "earnings momentum continues"},
            {"title": "TSLA earnings outlook", "snippet": "earnings and margin expansion"},
            {"title": "Macro rates update", "snippet": "inflation and rates"},
        ]

        trends = detector.extract_trends(results, min_frequency=2)

        self.assertIn("earnings", trends)
        self.assertNotIn("macro", trends)

    def test_score_rewards_trend_alignment(self):
        detector = TrendDetector()

        target = {"title": "TSLA earnings growth", "snippet": "earnings momentum"}
        all_results = [
            target,
            {"title": "TSLA earnings beat", "snippet": "earnings continue"},
            {"title": "Other market update", "snippet": "broad index move"},
        ]

        score = detector.score(target, all_results, query_terms={"tsla", "earnings"}, min_frequency=2, weight=0.5)

        self.assertGreater(score, 0.0)

    def test_score_returns_zero_when_no_trends(self):
        detector = TrendDetector()

        target = {"title": "Unique topic", "snippet": "single mention"}
        all_results = [
            target,
            {"title": "Another unique topic", "snippet": "different terms"},
        ]

        score = detector.score(target, all_results, min_frequency=3, weight=0.5)

        self.assertEqual(score, 0.0)

import unittest

from cognitive_folio.cognitive_folio.services.search import CrossSourceVerifier


class TestCrossSourceVerifier(unittest.TestCase):
    def test_returns_positive_score_for_multi_domain_corroboration(self):
        verifier = CrossSourceVerifier()

        target = {
            "title": "TSLA earnings beat expectations",
            "snippet": "revenue beat and margin expansion",
            "url": "https://reuters.com/markets/tsla-earnings",
        }
        others = [
            {
                "title": "WSJ: TSLA earnings beat expectations",
                "snippet": "revenue beat and stronger margins",
                "url": "https://www.wsj.com/markets/tsla-earnings",
            },
            {
                "title": "Bloomberg notes TSLA earnings beat",
                "snippet": "earnings beat with strong margin",
                "url": "https://www.bloomberg.com/news/tsla-earnings",
            },
        ]

        score = verifier.score(target, [target] + others, min_sources=1)

        self.assertGreater(score, 0.0)

    def test_applies_contradiction_penalty(self):
        verifier = CrossSourceVerifier()

        target = {
            "title": "TSLA earnings beat expectations",
            "snippet": "strong growth and upside outlook",
            "url": "https://reuters.com/markets/tsla",
        }
        contradictory = {
            "title": "TSLA missed earnings estimates",
            "snippet": "weak outlook and downgrade risk",
            "url": "https://www.wsj.com/markets/tsla",
        }

        low_penalty = verifier.score(
            target,
            [target, contradictory],
            min_sources=1,
            contradiction_penalty=0.05,
            confidence_boost=0.1,
        )
        high_penalty = verifier.score(
            target,
            [target, contradictory],
            min_sources=1,
            contradiction_penalty=0.5,
            confidence_boost=0.1,
        )

        self.assertGreater(low_penalty, high_penalty)

    def test_requires_minimum_source_count(self):
        verifier = CrossSourceVerifier()

        target = {
            "title": "Company guidance update",
            "snippet": "management reiterated annual guidance",
            "url": "https://example.com/a",
        }
        one_match = {
            "title": "Guidance update confirmed",
            "snippet": "annual guidance reiterated",
            "url": "https://example.org/b",
        }

        score = verifier.score(target, [target, one_match], min_sources=2)

        self.assertEqual(score, 0.0)

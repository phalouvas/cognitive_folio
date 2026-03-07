import unittest

from cognitive_folio.cognitive_folio.services.search import DomainAuthorityScorer


class TestDomainAuthorityScorer(unittest.TestCase):
    def test_scores_authoritative_domain(self):
        scorer = DomainAuthorityScorer()

        score = scorer.score("https://www.sec.gov/Archives/x")

        self.assertEqual(score, 1.0)

    def test_uses_custom_domain_weights(self):
        scorer = DomainAuthorityScorer()

        score = scorer.score(
            "https://research.example.com/report",
            domain_weights={"example.com": 0.92},
            default_weight=0.1,
        )

        self.assertEqual(score, 0.92)

    def test_falls_back_to_default_weight(self):
        scorer = DomainAuthorityScorer()

        score = scorer.score("https://unknown.test/resource", default_weight=0.33)

        self.assertEqual(score, 0.33)

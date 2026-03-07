import unittest

from cognitive_folio.cognitive_folio.services.search import QueryRefiner


class TestQueryRefiner(unittest.TestCase):
    def test_refine_removes_filler_and_compacts(self):
        refiner = QueryRefiner(enable_llm=False)

        refined = refiner.refine(
            "Can you please tell me about latest updates on Apple earnings outlook for 2026?",
            query_type="financial",
        )

        self.assertNotIn("can", refined)
        self.assertIn("earnings", refined)
        self.assertIn("apple", refined)

    def test_refine_appends_ticker_when_missing(self):
        refiner = QueryRefiner(enable_llm=False)

        refined = refiner.refine(
            "nvda valuation outlook",
            query_type="financial",
            ticker="NVDA",
        )

        self.assertIn("nvda", refined)

    def test_refine_uses_llm_fallback_when_enabled(self):
        refiner = QueryRefiner(enable_llm=True)

        refined = refiner.refine(
            "Tell me whatever you can",
            query_type="general",
            extraction_fallback=lambda text: "targeted refined query",
        )

        self.assertEqual(refined, "targeted refined query")

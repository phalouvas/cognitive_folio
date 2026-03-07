import unittest

from cognitive_folio.cognitive_folio.services.memory.knowledge_extractor import KnowledgeExtractor


class TestKnowledgeExtractor(unittest.TestCase):
    def test_extracts_tickers_numbers_and_action(self):
        extractor = KnowledgeExtractor()

        result = extractor.extract(
            prompt="Please rebalance AAPL and MSFT to 35% and 25%",
            response="AAPL momentum remains strong while MSFT looks stable.",
        )

        facts = result.get("facts") or []
        joined = " ".join(facts)
        self.assertIn("AAPL", joined)
        self.assertIn("MSFT", joined)
        self.assertIn("35%", joined)
        self.assertIn("rebalance", joined)

    def test_empty_input_returns_no_facts(self):
        extractor = KnowledgeExtractor()
        result = extractor.extract("", "")
        self.assertEqual(result, {"facts": []})

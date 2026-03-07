import unittest

from cognitive_folio.cognitive_folio.services.agent.query_analyzer import QueryAnalyzer
from cognitive_folio.cognitive_folio.services.agent.tool_recommender import ToolRecommender


class TestQueryAnalyzerAndToolRecommender(unittest.TestCase):
    def test_geopolitical_temporal_prompt_classifies_as_general_research(self):
        analyzer = QueryAnalyzer()
        analysis = analyzer.analyze(
            [
                {
                    "role": "user",
                    "content": "How long do you estimate the war between USA and Iran started in 2026 will last?",
                }
            ]
        )

        self.assertEqual(analysis["intent"], "general_research")
        self.assertTrue(analysis["requires_tools"])
        self.assertGreaterEqual(analysis["scores"]["geopolitical_hits"], 1)
        self.assertGreaterEqual(analysis["scores"]["temporal_hits"], 1)

    def test_general_assistance_does_not_recommend_all_tools(self):
        recommender = ToolRecommender()
        tools = [
            {"function": {"name": "web_search"}},
            {"function": {"name": "search_financial"}},
            {"function": {"name": "fetch_url_content"}},
        ]
        recommendation = recommender.recommend(
            analysis={"intent": "general_assistance", "requires_tools": False},
            tools=tools,
        )

        self.assertEqual(recommendation["recommended_tools"], [])

    def test_general_research_prefers_web_tools_only(self):
        recommender = ToolRecommender()
        tools = [
            {"function": {"name": "web_search"}},
            {"function": {"name": "search_financial"}},
            {"function": {"name": "fetch_url_content"}},
        ]
        recommendation = recommender.recommend(
            analysis={"intent": "general_research", "requires_tools": True},
            tools=tools,
        )

        self.assertIn("web_search", recommendation["recommended_tools"])
        self.assertIn("fetch_url_content", recommendation["recommended_tools"])
        self.assertNotIn("search_financial", recommendation["recommended_tools"])


if __name__ == "__main__":
    unittest.main()

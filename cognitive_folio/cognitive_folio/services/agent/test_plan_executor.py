import unittest
from types import SimpleNamespace

from cognitive_folio.cognitive_folio.services.agent.plan_executor import PlanExecutor


def _tool_call(name):
    return SimpleNamespace(function=SimpleNamespace(name=name))


class TestPlanExecutor(unittest.TestCase):
    def test_select_tool_calls_enforce_recommended_strict(self):
        executor = PlanExecutor()
        selected = executor.select_tool_calls(
            tool_calls=[_tool_call("search_financial")],
            max_per_round=5,
            recommended_tools=["web_search", "fetch_url_content"],
            enforce_recommended=True,
        )
        self.assertEqual(selected, [])

    def test_active_tools_for_round_filters_to_recommended(self):
        executor = PlanExecutor()
        tools = [
            {"function": {"name": "web_search"}},
            {"function": {"name": "search_financial"}},
            {"function": {"name": "fetch_url_content"}},
        ]

        active = executor.active_tools_for_round(
            tools=tools,
            round_index=1,
            max_rounds=8,
            recommended_tools=["web_search", "fetch_url_content"],
            enforce_recommended=True,
        )

        names = [(item.get("function") or {}).get("name") for item in active]
        self.assertEqual(names, ["web_search", "fetch_url_content"])

    def test_active_tools_for_last_round_stays_none(self):
        executor = PlanExecutor()
        active = executor.active_tools_for_round(
            tools=[{"function": {"name": "web_search"}}],
            round_index=8,
            max_rounds=8,
            recommended_tools=["web_search"],
            enforce_recommended=True,
        )
        self.assertIsNone(active)


if __name__ == "__main__":
    unittest.main()

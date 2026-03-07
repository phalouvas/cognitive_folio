import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from cognitive_folio.cognitive_folio.services.agent import (
    PlanExecutor,
    PlanGenerator,
    QueryAnalyzer,
    ToolRecommender,
)
from cognitive_folio.cognitive_folio.services.tool_orchestrator import ToolOrchestrator
from cognitive_folio.cognitive_folio.services.tooling import ToolComposer, ToolSelfCorrector


class TestAgentPlanningComponents(unittest.TestCase):
    def test_query_analyzer_detects_financial_research(self):
        analyzer = QueryAnalyzer()
        messages = [{"role": "user", "content": "Compare stock earnings and latest SEC 10-K filings for AAPL"}]
        analysis = analyzer.analyze(messages, config={"long_query_chars": 200})

        self.assertEqual(analysis["intent"], "financial_research")
        self.assertTrue(analysis["requires_tools"])

    def test_tool_recommender_filters_to_available_tools(self):
        recommender = ToolRecommender()
        analysis = {"intent": "general_research"}
        tools = [
            {"function": {"name": "web_search"}},
            {"function": {"name": "search_financial"}},
        ]

        recommendation = recommender.recommend(analysis, tools, config={"max_recommended_tools": 1})
        self.assertIn("web_search", recommendation["recommended_tools"])
        self.assertEqual(len(recommendation["recommended_tools"]), 1)

    def test_plan_generator_builds_steps(self):
        generator = PlanGenerator()
        plan = generator.generate(
            analysis={"intent": "financial_research", "complexity": "high"},
            recommendation={"recommended_tools": ["search_financial", "web_search"]},
            max_rounds=8,
            max_tool_calls_per_round=8,
            config={"max_plan_steps": 3},
        )

        self.assertEqual(plan["intent"], "financial_research")
        self.assertEqual(len(plan["steps"]), 3)

    def test_plan_executor_builds_system_message(self):
        executor = PlanExecutor()
        plan = {
            "intent": "general_research",
            "recommended_tools": ["web_search"],
            "steps": ["Understand user objective", "Collect data"],
        }
        message = executor.build_system_plan_message(plan)

        self.assertIn("Execution plan", message)
        self.assertIn("web_search", message)

    def test_tool_composer_resolves_last_result_placeholder(self):
        composer = ToolComposer()
        raw = '{"url": "${last:result.results.0.url}"}'
        context = {
            "last": {
                "ok": True,
                "result": {
                    "results": [{"url": "https://example.com/news"}],
                },
            }
        }

        composed = composer.compose_arguments_raw(raw, context)
        self.assertIn("https://example.com/news", composed)

    def test_tool_self_corrector_adds_missing_query(self):
        corrector = ToolSelfCorrector()
        corrected = corrector.build_retry_arguments(
            function_name="web_search",
            arguments_raw='{}',
            tool_result={"ok": False, "error_code": "validation_error"},
            context={"latest_user_message": "latest guidance for apple"},
        )
        self.assertEqual(corrected.get("query"), "latest guidance for apple")


class TestToolOrchestratorPlanningIntegration(unittest.TestCase):
    def _make_chat_message(self):
        chat_message = MagicMock()
        chat_message.name = "MSG-0001"
        chat_message.chat = "CHAT-0001"
        chat_message._get_tool_definitions.return_value = [
            {"function": {"name": "web_search"}},
            {"function": {"name": "search_financial"}},
        ]
        chat_message._get_max_tool_rounds.return_value = 2
        chat_message._get_max_tool_calls_per_round.return_value = 2
        chat_message._get_tool_result_max_chars.return_value = 500
        chat_message._accumulate_usage.side_effect = lambda aggregate_usage, usage_obj: None
        chat_message._content_looks_like_dsml.return_value = False
        chat_message._build_assistant_message_dict.side_effect = (
            lambda content, reasoning_content, tool_calls: {
                "role": "assistant",
                "content": content,
                "reasoning_content": reasoning_content,
                "tool_calls": tool_calls,
            }
        )
        chat_message._execute_tool_call.return_value = {"ok": True, "args": {}, "result": {"sample": 1}}
        chat_message._publish_chat_realtime.return_value = None
        chat_message._safe_json_loads.side_effect = lambda value, default=None: default if value in (None, "") else json.loads(value)
        chat_message._get_settings_manager.return_value = MagicMock(
            get_planner_config=MagicMock(
                return_value={
                    "enabled": True,
                    "inject_system_plan": True,
                    "enforce_recommended_tools": False,
                    "max_plan_steps": 6,
                    "max_recommended_tools": 4,
                }
            ),
            get_tool_execution_config=MagicMock(
                return_value={
                    "composition_enabled": True,
                    "self_correction_enabled": True,
                    "dynamic_registration_enabled": True,
                    "max_corrections_per_call": 1,
                }
            ),
        )

        # First response has no tool calls, so orchestrator exits early.
        assistant_message = SimpleNamespace(content="Final answer", reasoning_content="", tool_calls=[])
        first_choice = SimpleNamespace(message=assistant_message, finish_reason="stop")
        response_obj = SimpleNamespace(choices=[first_choice], usage=None)
        chat_message._create_non_stream_completion_with_retry.return_value = response_obj

        return chat_message

    def test_orchestrator_attaches_plan_to_usage(self):
        chat_message = self._make_chat_message()
        orchestrator = ToolOrchestrator(chat_message)

        messages = [{"role": "user", "content": "Find latest portfolio news and summarize risks"}]
        content, reasoning, finish_reason, usage, trace = orchestrator.run_tool_call_chain(
            client=MagicMock(),
            messages=messages,
            settings=MagicMock(),
            chat=MagicMock(),
            portfolio=None,
            security=None,
        )

        self.assertEqual(content, "Final answer")
        self.assertEqual(finish_reason, "stop")
        self.assertIn("plan", usage)
        self.assertIn("intent", usage["plan"])
        self.assertIn("planner", usage)
        self.assertIn("tool_execution", usage)
        self.assertIn("tool_metrics", usage)
        self.assertIsInstance(trace, list)

    def test_orchestrator_retries_failed_tool_call(self):
        chat_message = self._make_chat_message()

        def make_response_with_tool_call():
            tool_call = SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="web_search", arguments='{"query": ""}'),
            )
            assistant_message = SimpleNamespace(content="", reasoning_content="", tool_calls=[tool_call])
            first_choice = SimpleNamespace(message=assistant_message, finish_reason="tool_calls")
            return SimpleNamespace(choices=[first_choice], usage=None)

        final_assistant_message = SimpleNamespace(content="Final answer", reasoning_content="", tool_calls=[])
        final_choice = SimpleNamespace(message=final_assistant_message, finish_reason="stop")

        chat_message._create_non_stream_completion_with_retry.side_effect = [
            make_response_with_tool_call(),
            SimpleNamespace(choices=[final_choice], usage=None),
        ]

        call_results = [
            {"ok": False, "args": {}, "error_code": "validation_error", "error": "query is required"},
            {"ok": True, "args": {"query": "latest portfolio news"}, "result": {"count": 1}},
        ]
        chat_message._execute_tool_call.side_effect = call_results

        orchestrator = ToolOrchestrator(chat_message)
        messages = [{"role": "user", "content": "latest portfolio news"}]
        _, _, _, usage, trace = orchestrator.run_tool_call_chain(
            client=MagicMock(),
            messages=messages,
            settings=MagicMock(),
            chat=MagicMock(),
            portfolio=None,
            security=None,
        )

        self.assertEqual(chat_message._execute_tool_call.call_count, 2)
        self.assertEqual(len(trace), 1)
        self.assertTrue(trace[0]["retried"])
        self.assertIn("web_search", usage.get("tool_metrics", {}))

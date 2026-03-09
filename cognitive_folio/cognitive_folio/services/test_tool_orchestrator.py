import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cognitive_folio.cognitive_folio.services.agent.plan_executor import PlanExecutor
from cognitive_folio.cognitive_folio.services.tool_orchestrator import ToolOrchestrator


class _FakeSettingsManager:
    def get_planner_config(self):
        return {
            "enabled": True,
            "inject_system_plan": True,
            "enforce_recommended_tools": False,
            "max_recommended_tools": 4,
        }

    def get_tool_execution_config(self):
        return {
            "composition_enabled": True,
            "self_correction_enabled": True,
            "dynamic_registration_enabled": True,
            "max_corrections_per_call": 1,
        }


def _make_response(content, tool_calls=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, reasoning_content="", tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=None)


def _make_tool_call(name="web_search", call_id="call_1", args='{"query": "test"}'):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=args))


class TestToolOrchestrator(unittest.TestCase):
    def _make_chat_message(self, web_search_enabled=True):
        chat_message = MagicMock()
        chat_message.name = "test-msg"
        chat_message.chat = "test-chat"
        chat_message.model = "deepseek-chat"
        chat_message.web_search = web_search_enabled

        chat_message._get_tool_definitions.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ]
        chat_message._get_max_tool_rounds.return_value = 3
        chat_message._get_max_tool_calls_per_round.return_value = 4
        chat_message._get_tool_result_max_chars.return_value = 8000
        chat_message._get_settings_manager.return_value = _FakeSettingsManager()

        chat_message._build_assistant_message_dict.side_effect = lambda content, reasoning, tool_calls: {
            "role": "assistant",
            "content": content,
            "reasoning_content": reasoning,
            "tool_calls": tool_calls,
        }
        chat_message._content_looks_like_dsml.return_value = False
        chat_message._accumulate_usage.side_effect = lambda *_args, **_kwargs: None
        chat_message._publish_chat_realtime.side_effect = lambda *_args, **_kwargs: None
        chat_message._is_reasoner_model.return_value = False
        chat_message._execute_tool_call.return_value = {"ok": True, "data": "search result"}

        return chat_message

    def _make_orchestrator(self, max_rounds=3):
        """Create a ToolOrchestrator with agent components mocked except PlanExecutor."""
        chat_message = self._make_chat_message()
        chat_message._get_max_tool_rounds.return_value = max_rounds

        orch = ToolOrchestrator.__new__(ToolOrchestrator)
        orch.chat_message = chat_message
        orch.plan_executor = PlanExecutor()
        orch.query_analyzer = MagicMock()
        orch.tool_recommender = MagicMock()
        orch.plan_generator = MagicMock()
        orch.tool_composer = MagicMock()
        orch.tool_metrics_store = MagicMock()
        orch.tool_self_corrector = MagicMock()

        orch.query_analyzer.analyze.return_value = {
            "latest_user_message": "test query",
            "intent": "research",
            "scores": {},
        }
        orch.tool_recommender.recommend.return_value = {"recommended_tools": []}
        orch.plan_generator.generate.return_value = {}
        orch.tool_composer.compose_arguments_raw.side_effect = lambda raw, ctx: raw
        orch.tool_self_corrector.build_retry_arguments.return_value = None
        orch.tool_metrics_store.persist_daily_rollups.return_value = {}

        return orch, chat_message

    def _run_chain(self, orch, chat_message, responses, max_rounds=None):
        """Helper: patch frappe and run run_tool_call_chain, returning the result tuple."""
        if max_rounds is not None:
            chat_message._get_max_tool_rounds.return_value = max_rounds
        chat_message._create_non_stream_completion_with_retry.side_effect = responses
        settings = MagicMock()
        settings.chat_default_max_tokens = 4000

        with patch("cognitive_folio.cognitive_folio.services.tool_orchestrator.frappe") as mock_frappe:
            mock_frappe.logger.return_value = MagicMock()
            mock_frappe.utils.now_datetime.return_value = datetime.datetime(2026, 3, 9, 12, 0, 0)
            return orch.run_tool_call_chain(
                client=MagicMock(),
                messages=[{"role": "user", "content": "What is the gold price?"}],
                settings=settings,
                chat="test-chat",
                portfolio=None,
                security=None,
            )

    # ------------------------------------------------------------------
    # Synthesis nudge timing
    # ------------------------------------------------------------------

    def test_max_rounds_3_gives_two_tool_rounds_then_synthesis(self):
        """With max_rounds=3, the model uses tools in rounds 1-2 and synthesises at round 3.
        Expansion always fires when tools were used, so one extra response is needed."""
        orch, chat_msg = self._make_orchestrator(max_rounds=3)
        tool_call = _make_tool_call()
        first_synthesis = "## Gold Market Analysis\n\nInitial findings.\n"
        expanded = "## Gold Market Analysis\n\n" + "Detailed analysis of gold prices.\n" * 50

        responses = [
            _make_response("", [tool_call], "tool_calls"),   # round 1: tool call
            _make_response("", [tool_call], "tool_calls"),   # round 2: tool call
            _make_response(first_synthesis, [], "stop"),      # round 3: synthesis
            _make_response(expanded, [], "stop"),             # expansion pass
        ]
        content, _reasoning, finish, usage, trace = self._run_chain(orch, chat_msg, responses)

        self.assertEqual(content, expanded)
        self.assertEqual(finish, "stop")
        self.assertEqual(usage["tool_rounds"], 3)
        # Two tool executions — one per tool-calling round
        self.assertEqual(len(trace), 2)

    def test_max_rounds_2_gives_one_tool_round_then_synthesis(self):
        """With max_rounds=2, the model uses tools in round 1 and synthesises at round 2.
        Expansion always fires when tools were used."""
        orch, chat_msg = self._make_orchestrator(max_rounds=2)
        tool_call = _make_tool_call()
        first_synthesis = "## Analysis\n\nInitial findings.\n"
        expanded = "## Analysis\n\n" + "Content.\n" * 120

        responses = [
            _make_response("", [tool_call], "tool_calls"),  # round 1: tool call
            _make_response(first_synthesis, [], "stop"),     # round 2: synthesis
            _make_response(expanded, [], "stop"),            # expansion pass
        ]
        content, _reasoning, finish, usage, trace = self._run_chain(orch, chat_msg, responses)

        self.assertEqual(content, expanded)
        self.assertEqual(usage["tool_rounds"], 2)
        self.assertEqual(len(trace), 1)

    def test_max_rounds_1_direct_synthesis_no_tools(self):
        """With max_rounds=1, the synthesis nudge fires in round 1 — tools are suppressed.
        No tool_trace means no expansion; response returned directly."""
        orch, chat_msg = self._make_orchestrator(max_rounds=1)
        rich_synthesis = "## Direct Answer\n\n" + "Content.\n" * 90  # >800 chars

        responses = [
            _make_response(rich_synthesis, [], "stop"),  # round 1: synthesis (no tools, no expansion)
        ]
        content, _reasoning, finish, usage, trace = self._run_chain(orch, chat_msg, responses)

        self.assertEqual(content, rich_synthesis)
        self.assertEqual(usage["tool_rounds"], 1)
        self.assertEqual(len(trace), 0)

    def test_synthesis_nudge_injected_at_max_round_not_earlier(self):
        """Synthesis nudge message appears in the messages list at max_rounds only."""
        orch, chat_msg = self._make_orchestrator(max_rounds=3)
        tool_call = _make_tool_call()
        first_synthesis = "## Analysis\n\nInitial findings.\n"
        expanded = "## Analysis\n\n" + "Content.\n" * 180

        captured_messages = []

        original_side_effect = [
            _make_response("", [tool_call], "tool_calls"),
            _make_response("", [tool_call], "tool_calls"),
            _make_response(first_synthesis, [], "stop"),
            _make_response(expanded, [], "stop"),  # expansion pass
        ]

        call_count = 0

        def capture_and_respond(client, messages, settings, tools):
            nonlocal call_count
            captured_messages.append([m.copy() if isinstance(m, dict) else m for m in messages])
            result = original_side_effect[call_count]
            call_count += 1
            return result

        chat_msg._create_non_stream_completion_with_retry.side_effect = capture_and_respond
        settings = MagicMock()
        settings.chat_default_max_tokens = 4000

        with patch("cognitive_folio.cognitive_folio.services.tool_orchestrator.frappe") as mock_frappe:
            mock_frappe.logger.return_value = MagicMock()
            mock_frappe.utils.now_datetime.return_value = datetime.datetime(2026, 3, 9, 12, 0, 0)
            orch.run_tool_call_chain(
                client=MagicMock(),
                messages=[{"role": "user", "content": "test"}],
                settings=settings,
                chat="test-chat",
                portfolio=None,
                security=None,
            )

        def _has_final_synthesis_directive(msgs):
            return any(
                isinstance(m, dict)
                and m.get("role") == "system"
                and "FINAL SYNTHESIS REQUIRED" in (m.get("content") or "")
                for m in msgs
            )

        # Round 1 must NOT have the FINAL SYNTHESIS directive
        self.assertFalse(_has_final_synthesis_directive(captured_messages[0]))
        # Round 2 must NOT have the FINAL SYNTHESIS directive
        self.assertFalse(_has_final_synthesis_directive(captured_messages[1]))
        # Round 3 MUST have the FINAL SYNTHESIS directive
        self.assertTrue(_has_final_synthesis_directive(captured_messages[2]))

    def test_tools_suppressed_after_nudge(self):
        """Once synthesis_nudge_sent=True, active_tools is None for the synthesis round."""
        orch, chat_msg = self._make_orchestrator(max_rounds=2)
        tool_call = _make_tool_call()
        rich_synthesis = "## Analysis\n\n" + "Content.\n" * 120  # >1000 chars (round-2 nudge threshold)

        tools_passed = []

        def capture_tools(client, messages, settings, tools):
            tools_passed.append(tools)
            if len(tools_passed) == 1:
                return _make_response("", [tool_call], "tool_calls")
            return _make_response(rich_synthesis, [], "stop")

        chat_msg._create_non_stream_completion_with_retry.side_effect = capture_tools
        settings = MagicMock()
        settings.chat_default_max_tokens = 4000

        with patch("cognitive_folio.cognitive_folio.services.tool_orchestrator.frappe") as mock_frappe:
            mock_frappe.logger.return_value = MagicMock()
            mock_frappe.utils.now_datetime.return_value = datetime.datetime(2026, 3, 9, 12, 0, 0)
            orch.run_tool_call_chain(
                client=MagicMock(),
                messages=[{"role": "user", "content": "test"}],
                settings=settings,
                chat="test-chat",
                portfolio=None,
                security=None,
            )

        # Round 1: tools should be available (list)
        self.assertIsNotNone(tools_passed[0])
        # Round 2 (synthesis round): tools must be None
        self.assertIsNone(tools_passed[1])

    # ------------------------------------------------------------------
    # Weak synthesis detection
    # ------------------------------------------------------------------

    def test_is_weak_synthesis_empty_content(self):
        orch, _ = self._make_orchestrator()
        self.assertTrue(orch._is_weak_synthesis_content("", 2))
        self.assertTrue(orch._is_weak_synthesis_content(None, 2))

    def test_is_weak_synthesis_short_content_after_two_rounds(self):
        orch, _ = self._make_orchestrator()
        self.assertTrue(orch._is_weak_synthesis_content("Very short content.", 2))

    def test_is_weak_synthesis_short_content_flagged_at_single_round_threshold(self):
        orch, _ = self._make_orchestrator()
        # Default formula for 1 round: max(200, 1*400) = 400 chars.
        # Content under that threshold is flagged.
        self.assertTrue(orch._is_weak_synthesis_content("Very short content.", 1))
        # Content >= 400 chars is fine at round 1
        self.assertFalse(orch._is_weak_synthesis_content("x" * 401, 1))

    def test_is_weak_synthesis_long_content_not_flagged(self):
        orch, _ = self._make_orchestrator()
        # Default formula: max(200, 3*400) = 1200 chars min.
        # Build content well above 1200 chars.
        long_content = "## Analysis\n\n" + "Detail.\n" * 200  # ~1614 chars
        self.assertFalse(orch._is_weak_synthesis_content(long_content, 3))

    def test_is_weak_synthesis_detects_let_me_opener_without_structure(self):
        """Content starting with 'Let me' and lacking headings/bullets is flagged as artifact."""
        orch, _ = self._make_orchestrator()
        garbage = "Let me get more specific data...gold US dollar safe haven assets VIX\n5"
        self.assertTrue(orch._is_weak_synthesis_content(garbage, 1))

    def test_is_weak_synthesis_let_me_with_structure_not_flagged(self):
        """'Let me' opener + structural markers and sufficient length is NOT a leaked artifact."""
        orch, _ = self._make_orchestrator()
        # Content must be > 400 chars (round-1 default threshold) AND have structural markers
        structured = "Let me summarize:\n\n## Key Findings\n\n" + "- Gold up 5%\n- VIX elevated\n" * 20
        self.assertFalse(orch._is_weak_synthesis_content(structured, 1))

    def test_is_weak_synthesis_planning_phrases_detected(self):
        orch, _ = self._make_orchestrator()
        self.assertTrue(orch._is_weak_synthesis_content("Searching for gold ETF data markets", 1))
        self.assertTrue(orch._is_weak_synthesis_content("I need to look up the current price", 1))

    def test_is_weak_synthesis_explicit_min_chars_overrides_default(self):
        """Caller-supplied min_chars takes precedence over the default formula."""
        orch, _ = self._make_orchestrator()
        # 500-char content fails round-3 default (1200 chars) but passes when min_chars=400
        medium = "x" * 500
        self.assertTrue(orch._is_weak_synthesis_content(medium, 3))
        self.assertFalse(orch._is_weak_synthesis_content(medium, 3, min_chars=400))
        self.assertTrue(orch._is_weak_synthesis_content(medium, 3, min_chars=600))

    def test_nudge_aware_min_chars_catches_thin_synthesis_after_two_tool_rounds(self):
        """Thin synthesis (~334 tokens / ~1300 chars) is caught by nudge threshold at round 3."""
        orch, _ = self._make_orchestrator()
        # round_index=3: nudge_min_chars = max(800, 3*500) = 1500
        thin_but_wordy = "x" * 1300  # passes old 200-char check, fails new 1500 nudge check
        self.assertTrue(orch._is_weak_synthesis_content(thin_but_wordy, 3, min_chars=max(800, 3 * 500)))
        rich = "x" * 1501
        self.assertFalse(orch._is_weak_synthesis_content(rich, 3, min_chars=max(800, 3 * 500)))

    # ------------------------------------------------------------------
    # Natural early-stop weak synthesis check (tool_trace non-empty)
    # ------------------------------------------------------------------

    def test_weak_natural_stop_triggers_forced_synthesis(self):
        """If model stops calling tools early and produces garbage, forced synthesis fires."""
        orch, chat_msg = self._make_orchestrator(max_rounds=3)
        tool_call = _make_tool_call()
        garbage = "Let me get more data on gold and VIX trends"
        forced = "## Gold Analysis\n\n" + "Detailed market analysis.\n" * 35  # >800 chars (round-2 default threshold)

        responses = [
            _make_response("", [tool_call], "tool_calls"),    # round 1: tool call
            _make_response(garbage, [], "stop"),               # round 2: garbage early stop
            # forced synthesis pass
            _make_response(forced, [], "stop"),
        ]
        content, _reasoning, _finish, _usage, trace = self._run_chain(orch, chat_msg, responses)

        # Forced synthesis content should be returned, not the garbage
        self.assertEqual(content, forced)
        # Only 1 tool was executed (round 1)
        self.assertEqual(len(trace), 1)

    # ------------------------------------------------------------------
    # Forced synthesis retry when first attempt is still weak
    # ------------------------------------------------------------------

    def test_forced_synthesis_retries_when_still_weak(self):
        """_force_synthesis_response retries once when first forced content is still weak."""
        orch, chat_msg = self._make_orchestrator(max_rounds=3)
        tool_call = _make_tool_call()
        # Round 1-2: use tools; round 3: nudge fires, returns weak garbage
        weak_synthesis = "Let me summarize the data found so far query"
        # first forced pass: still weak
        still_weak = "Searching for more info on results"
        # second forced pass: good content
        good = "## Final Analysis\n\n" + "Rich market analysis.\n" * 20

        responses = [
            _make_response("", [tool_call], "tool_calls"),   # round 1
            _make_response("", [tool_call], "tool_calls"),   # round 2
            _make_response(weak_synthesis, [], "stop"),       # round 3 (synthesis nudge)
            _make_response(still_weak, [], "stop"),           # _force_synthesis_response first pass
            _make_response(good, [], "stop"),                 # _force_synthesis_response retry
        ]
        content, _reasoning, _finish, _usage, _trace = self._run_chain(orch, chat_msg, responses)

        self.assertEqual(content, good)

    # ------------------------------------------------------------------
    # Forced synthesis max_tokens
    # ------------------------------------------------------------------

    def test_force_synthesis_uses_8192_max_tokens_for_chat_fallback(self):
        """deepseek-chat fallback in _force_synthesis_response uses at least 8192 tokens."""
        orch, chat_msg = self._make_orchestrator(max_rounds=3)
        tool_call = _make_tool_call()
        chat_msg.model = "deepseek-reasoner"
        chat_msg._is_reasoner_model.return_value = True
        weak_synthesis = "Let me synthesize the gathered data now"
        good = "## Analysis\n\n" + "Full analysis.\n" * 90  # >1200 chars (round-3 default threshold in _force_synthesis_response)

        captured_kwargs = {}

        def fake_chat_create(**kwargs):
            captured_kwargs.update(kwargs)
            msg = SimpleNamespace(content=good, reasoning_content="")
            choice = SimpleNamespace(message=msg, finish_reason="stop")
            return SimpleNamespace(choices=[choice], usage=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = fake_chat_create

        responses = [
            _make_response("", [tool_call], "tool_calls"),
            _make_response("", [tool_call], "tool_calls"),
            _make_response(weak_synthesis, [], "stop"),
        ]
        chat_msg._create_non_stream_completion_with_retry.side_effect = responses
        settings = MagicMock()
        settings.chat_default_max_tokens = 4000

        with patch("cognitive_folio.cognitive_folio.services.tool_orchestrator.frappe") as mock_frappe:
            mock_frappe.logger.return_value = MagicMock()
            mock_frappe.utils.now_datetime.return_value = datetime.datetime(2026, 3, 9, 12, 0, 0)
            orch.run_tool_call_chain(
                client=mock_client,
                messages=[{"role": "user", "content": "How is gold performing?"}],
                settings=settings,
                chat="test-chat",
                portfolio=None,
                security=None,
            )

        self.assertGreaterEqual(captured_kwargs.get("max_tokens", 0), 8192)


if __name__ == "__main__":
    unittest.main()

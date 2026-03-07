import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

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

        return chat_message

    def test_forces_realtime_web_search_for_weather_now_query(self):
        chat_message = self._make_chat_message(web_search_enabled=True)
        chat_message._create_non_stream_completion_with_retry.side_effect = [
            _make_response("I cannot access realtime weather."),
            _make_response("Current weather in Larnaka is 21C with light wind."),
        ]
        chat_message._execute_tool_call.return_value = {
            "ok": True,
            "args": {"query": "What is the weather now in Larnaka Cyprus?"},
            "result": {
                "query": "What is the weather now in Larnaka Cyprus?",
                "count": 2,
                "results": [],
            },
        }

        orchestrator = ToolOrchestrator(chat_message)
        response, _reasoning, _finish, usage, trace = orchestrator.run_tool_call_chain(
            client=MagicMock(),
            messages=[{"role": "user", "content": "What is the weather now in Larnaka Cyprus?"}],
            settings=MagicMock(),
            chat=MagicMock(name="chat-doc"),
            portfolio=None,
            security=None,
        )

        self.assertIn("Current weather in Larnaka", response)
        chat_message._execute_tool_call.assert_called_once()
        self.assertEqual(chat_message._execute_tool_call.call_args.kwargs.get("function_name"), "web_search")
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["tool"], "web_search")
        self.assertTrue(trace[0].get("forced"))
        self.assertTrue(usage["tool_execution"]["forced_realtime_web_search"])

    def test_does_not_force_when_web_search_disabled(self):
        chat_message = self._make_chat_message(web_search_enabled=False)
        chat_message._create_non_stream_completion_with_retry.return_value = _make_response(
            "I cannot access realtime weather."
        )

        orchestrator = ToolOrchestrator(chat_message)
        response, _reasoning, _finish, usage, trace = orchestrator.run_tool_call_chain(
            client=MagicMock(),
            messages=[{"role": "user", "content": "What is the weather now in Larnaka Cyprus?"}],
            settings=MagicMock(),
            chat=MagicMock(name="chat-doc"),
            portfolio=None,
            security=None,
        )

        self.assertEqual(response, "I cannot access realtime weather.")
        chat_message._execute_tool_call.assert_not_called()
        self.assertEqual(trace, [])
        self.assertFalse(usage["tool_execution"]["forced_realtime_web_search"])

    def test_conflict_duration_query_detection(self):
        orchestrator = ToolOrchestrator(self._make_chat_message(web_search_enabled=True))
        self.assertTrue(
            orchestrator._is_conflict_duration_query(
                "How long do you estimate the war between USA/Israel and Iran will last?"
            )
        )
        self.assertFalse(orchestrator._is_conflict_duration_query("How is portfolio risk calculated?"))

    def test_conflict_duration_mode_sets_usage_flag(self):
        chat_message = self._make_chat_message(web_search_enabled=True)
        chat_message._create_non_stream_completion_with_retry.return_value = _make_response(
            "Insufficient evidence, but here is a scenario estimate."
        )

        orchestrator = ToolOrchestrator(chat_message)
        _response, _reasoning, _finish, usage, _trace = orchestrator.run_tool_call_chain(
            client=MagicMock(),
            messages=[{"role": "user", "content": "How long do you estimate the war between USA and Iran will last?"}],
            settings=MagicMock(),
            chat=MagicMock(name="chat-doc"),
            portfolio=None,
            security=None,
        )

        self.assertTrue(usage["tool_execution"]["conflict_duration_mode"])

    def test_conflict_duration_rewrite_overrides_draft(self):
        chat_message = self._make_chat_message(web_search_enabled=True)
        chat_message._create_non_stream_completion_with_retry.side_effect = [
            _make_response(
                "Draft: this does not exist.",
                tool_calls=[
                    SimpleNamespace(
                        id="call_1",
                        function=SimpleNamespace(
                            name="web_search",
                            arguments='{"query": "iran israel war duration"}',
                        ),
                    )
                ],
                finish_reason="tool_calls",
            ),
            _make_response("Draft answer with no verification details."),
            _make_response("Final rewrite: I could not verify from retrieved sources. Confidence: low."),
        ]
        chat_message._execute_tool_call.return_value = {
            "ok": True,
            "args": {"query": "iran israel war duration"},
            "result": {"count": 1, "results": []},
        }

        orchestrator = ToolOrchestrator(chat_message)
        response, _reasoning, _finish, usage, trace = orchestrator.run_tool_call_chain(
            client=MagicMock(),
            messages=[{"role": "user", "content": "How long would the war between Iran and Israel last?"}],
            settings=MagicMock(),
            chat=MagicMock(name="chat-doc"),
            portfolio=None,
            security=None,
        )

        self.assertIn("I could not verify", response)
        self.assertTrue(usage["tool_execution"]["conflict_duration_mode"])
        self.assertTrue(usage["tool_execution"]["conflict_duration_rewrite"])
        self.assertEqual(len(trace), 1)


if __name__ == "__main__":
    unittest.main()

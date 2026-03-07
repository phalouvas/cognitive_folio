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


if __name__ == "__main__":
    unittest.main()

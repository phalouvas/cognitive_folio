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



if __name__ == "__main__":
    unittest.main()

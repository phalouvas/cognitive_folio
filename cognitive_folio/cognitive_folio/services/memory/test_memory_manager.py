import unittest
from unittest.mock import MagicMock

from cognitive_folio.cognitive_folio.services.memory.memory_manager import MemoryManager


class TestMemoryManager(unittest.TestCase):
    def test_disabled_memory_returns_empty(self):
        manager = MemoryManager(MagicMock())
        settings_manager = MagicMock()
        settings_manager.get_memory_config.return_value = {"enabled": False}

        context = manager.get_context_for_prompt("CHAT-1", settings_manager, current_prompt="hello")
        result = manager.record_turn("CHAT-1", "hi", "there", settings_manager)

        self.assertEqual(context, "")
        self.assertFalse(result["stored"])

    def test_enabled_memory_delegates(self):
        manager = MemoryManager(MagicMock())
        manager.conversation_memory = MagicMock()
        manager.vector_memory = MagicMock()
        manager.knowledge_extractor = MagicMock()
        manager.knowledge_extractor.extract.return_value = {"facts": ["Tickers discussed: AAPL"]}
        manager.conversation_memory.get_context.return_value = "memo"
        manager.conversation_memory.record_turn.return_value = {"stored": True}
        manager.vector_memory.get_context.return_value = "vector memo"
        manager.vector_memory.record_turn.return_value = {"stored": True}

        settings_manager = MagicMock()
        settings_manager.get_memory_config.return_value = {"enabled": True}

        context = manager.get_context_for_prompt(
            "CHAT-1",
            settings_manager,
            current_prompt="hello",
            context={"portfolio": "P1", "security": "S1"},
        )
        result = manager.record_turn(
            "CHAT-1",
            "hi",
            "there",
            settings_manager,
            context={"portfolio": "P1", "security": "S1"},
        )

        self.assertIn("Short-term", context)
        self.assertIn("Relevant history", context)
        self.assertTrue(result["stored"])
        manager.conversation_memory.record_turn.assert_called_once()
        manager.vector_memory.record_turn.assert_called_once()
        _, kwargs = manager.conversation_memory.record_turn.call_args
        self.assertEqual(kwargs.get("metadata"), {"facts": ["Tickers discussed: AAPL"]})

from .conversation_memory import ConversationMemory
from .knowledge_extractor import KnowledgeExtractor
from .vector_memory import VectorMemory


class MemoryManager:
    """Coordinate memory retrieval and persistence for chat flows."""

    def __init__(self, chat_message):
        self.chat_message = chat_message
        self.conversation_memory = ConversationMemory()
        self.vector_memory = VectorMemory()
        self.knowledge_extractor = KnowledgeExtractor()

    def get_context_for_prompt(self, chat_name, settings_manager, current_prompt="", context=None):
        config = settings_manager.get_memory_config() if settings_manager else {}
        if not config.get("enabled", True):
            return ""

        short_context = self.conversation_memory.get_context(
            chat_name=chat_name,
            config=config,
            current_prompt=current_prompt,
        )

        vector_context = self.vector_memory.get_context(
            chat_name=chat_name,
            current_prompt=current_prompt,
            config=config,
            context=context or {},
        )

        sections = []
        if short_context:
            sections.append(f"Short-term:\n{short_context}")
        if vector_context:
            sections.append(f"Relevant history:\n{vector_context}")
        return "\n\n".join(sections).strip()

    def record_turn(self, chat_name, prompt, response, settings_manager, context=None):
        config = settings_manager.get_memory_config() if settings_manager else {}
        if not config.get("enabled", True):
            return {"stored": False, "reason": "disabled"}

        metadata = self.knowledge_extractor.extract(prompt=prompt, response=response)
        short_result = self.conversation_memory.record_turn(
            chat_name=chat_name,
            prompt=prompt,
            response=response,
            config=config,
            metadata=metadata,
        )

        vector_result = self.vector_memory.record_turn(
            chat_name=chat_name,
            prompt=prompt,
            response=response,
            config=config,
            metadata=metadata,
            context=context or {},
        )

        return {
            "stored": bool((short_result or {}).get("stored") or (vector_result or {}).get("stored")),
            "short_term": short_result,
            "vector": vector_result,
        }

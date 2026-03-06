
import re


class TokenManager:
    """Conversation trimming, summary helpers, and token-related utilities."""

    def __init__(self, chat_message):
        self.chat_message = chat_message

    def count_markdown_search_results(self, search_results_markdown):
        if not search_results_markdown:
            return 0
        return len(re.findall(r"^\d+\.\s", search_results_markdown, flags=re.MULTILINE))

    def clear_reasoning_content(self, messages):
        cleaned_messages = []
        for message in messages or []:
            if not isinstance(message, dict):
                cleaned_messages.append(message)
                continue

            cloned = dict(message)
            if cloned.get("role") == "assistant" and "reasoning_content" in cloned:
                cloned.pop("reasoning_content", None)
            cleaned_messages.append(cloned)

        return cleaned_messages

    def summarize_conversation(self, overflow_messages):
        if not overflow_messages:
            return ""

        lines = []
        for item in reversed(overflow_messages[-8:]):
            user_text = (item.get("prompt") or "").strip()
            assistant_text = (item.get("response") or "").strip()
            if user_text:
                lines.append(f"User: {user_text[:240]}")
            if assistant_text:
                lines.append(f"Assistant: {assistant_text[:320]}")

        summary = "\n".join(lines)
        if len(summary) > 2400:
            summary = summary[:2400] + "..."
        return summary

    def is_complex_query(self, prompt_text):
        prompt_text = (prompt_text or "").strip()
        if not prompt_text:
            return False

        if len(prompt_text) >= 1200:
            return True

        complex_markers = [
            "analyze",
            "compare",
            "valuation",
            "scenario",
            "sensitivity",
            "portfolio",
            "risk",
            "forecast",
        ]
        lowered = prompt_text.lower()
        matches = sum(1 for marker in complex_markers if marker in lowered)
        return matches >= 2

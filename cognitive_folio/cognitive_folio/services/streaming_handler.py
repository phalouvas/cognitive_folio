import time

import frappe

from cognitive_folio.utils.markdown import safe_markdown_to_html


class StreamingHandler:
    """Handles streamed model responses with periodic persistence."""

    def __init__(self, chat_message):
        self.chat_message = chat_message

    def process_stream(self, response, settings):
        full_response = ""
        reasoning_content = ""
        finish_reason = None
        last_saved_response_length = 0
        last_saved_reasoning_length = 0
        last_flush_at = time.time()

        stream_flush_interval_seconds = self.chat_message._get_stream_flush_interval_seconds(settings)
        stream_flush_min_char_delta = self.chat_message._get_stream_flush_min_char_delta(settings)

        for chunk in response:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            content_updated = False
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason

            if hasattr(choice.delta, "reasoning_content") and choice.delta.reasoning_content:
                reasoning_content += choice.delta.reasoning_content
                content_updated = True

            if hasattr(choice.delta, "content") and choice.delta.content:
                full_response += choice.delta.content
                content_updated = True

            if not content_updated:
                continue

            now_ts = time.time()
            response_delta = len(full_response) - last_saved_response_length
            reasoning_delta = len(reasoning_content) - last_saved_reasoning_length
            should_flush = (
                response_delta >= stream_flush_min_char_delta
                or reasoning_delta >= stream_flush_min_char_delta
                or (now_ts - last_flush_at) >= stream_flush_interval_seconds
            )

            if not should_flush:
                continue

            self.chat_message.response = full_response
            self.chat_message.response_html = safe_markdown_to_html(full_response)
            self.chat_message.reasoning = reasoning_content
            self.chat_message.db_update()
            frappe.db.commit()

            last_saved_response_length = len(full_response)
            last_saved_reasoning_length = len(reasoning_content)
            last_flush_at = now_ts

            self.chat_message._publish_chat_realtime(
                event_name="cf_streaming_update",
                payload={
                    "message_id": self.chat_message.name,
                    "chat_id": self.chat_message.chat,
                    "message": full_response,
                    "reasoning": reasoning_content,
                    "status": "streaming",
                },
            )

        return full_response, reasoning_content, finish_reason

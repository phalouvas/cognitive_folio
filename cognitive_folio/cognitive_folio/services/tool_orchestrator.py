import json
import time

import frappe


class ToolOrchestrator:
    """Coordinates iterative tool-calling loops for chat completions."""

    def __init__(self, chat_message):
        self.chat_message = chat_message

    def run_tool_call_chain(self, client, messages, settings, chat, portfolio, security):
        tools = self.chat_message._get_tool_definitions()
        max_rounds = self.chat_message._get_max_tool_rounds(settings)
        max_tool_calls_per_round = self.chat_message._get_max_tool_calls_per_round(settings)
        tool_result_max_chars = self.chat_message._get_tool_result_max_chars(settings)

        all_reasoning_parts = []
        tool_trace = []
        last_finish_reason = None
        aggregate_usage = {
            "tool_rounds": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        synthesis_nudge_sent = False

        for round_index in range(1, max_rounds + 1):
            if not synthesis_nudge_sent and (max_rounds - round_index) < 2:
                messages.append({
                    "role": "system",
                    "content": (
                        "You have used several research rounds. "
                        "Stop calling tools now and write your final, complete answer "
                        "based on everything you have gathered so far."
                    ),
                })
                synthesis_nudge_sent = True

            active_tools = None if round_index == max_rounds else tools
            response = self.chat_message._create_non_stream_completion_with_retry(
                client=client,
                messages=messages,
                settings=settings,
                tools=active_tools,
            )
            aggregate_usage["tool_rounds"] = round_index
            self.chat_message._accumulate_usage(aggregate_usage, getattr(response, "usage", None))

            if not response.choices:
                raise RuntimeError("Tool-chain completion returned no choices")

            choice = response.choices[0]
            message = choice.message
            assistant_content = getattr(message, "content", None) or ""
            reasoning_content = getattr(message, "reasoning_content", None) or ""
            if reasoning_content:
                all_reasoning_parts.append(reasoning_content)

            tool_calls = list(getattr(message, "tool_calls", None) or [])
            last_finish_reason = getattr(choice, "finish_reason", None)

            if not tool_calls:
                if self.chat_message._content_looks_like_dsml(assistant_content):
                    messages.append(self.chat_message._build_assistant_message_dict("", reasoning_content, []))
                    break
                messages.append(self.chat_message._build_assistant_message_dict(assistant_content, reasoning_content, []))
                return assistant_content, "\n\n".join(all_reasoning_parts), last_finish_reason, aggregate_usage, tool_trace

            assistant_tool_calls = []
            for tool_call in tool_calls[:max_tool_calls_per_round]:
                call_id = getattr(tool_call, "id", None)
                function_obj = getattr(tool_call, "function", None)
                function_name = getattr(function_obj, "name", "") if function_obj else ""
                arguments_raw = getattr(function_obj, "arguments", "{}") if function_obj else "{}"
                assistant_tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": arguments_raw,
                    },
                })

            messages.append(self.chat_message._build_assistant_message_dict(assistant_content, reasoning_content, assistant_tool_calls))

            for tool_call in tool_calls[:max_tool_calls_per_round]:
                call_started = time.time()
                call_id = getattr(tool_call, "id", None)
                function_obj = getattr(tool_call, "function", None)
                function_name = getattr(function_obj, "name", "") if function_obj else ""
                arguments_raw = getattr(function_obj, "arguments", "{}") if function_obj else "{}"

                tool_result = self.chat_message._execute_tool_call(
                    function_name=function_name,
                    arguments_raw=arguments_raw,
                    chat=chat,
                    portfolio=portfolio,
                    security=security,
                )

                result_content = json.dumps(tool_result, ensure_ascii=False, default=str)
                if len(result_content) > tool_result_max_chars:
                    result_content = result_content[:tool_result_max_chars] + "..."

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": function_name,
                    "content": result_content,
                })

                tool_trace.append({
                    "round": round_index,
                    "tool": function_name,
                    "call_id": call_id,
                    "ok": bool(tool_result.get("ok", False)),
                    "duration_ms": round((time.time() - call_started) * 1000, 2),
                    "args": tool_result.get("args", {}),
                    "error_code": tool_result.get("error_code"),
                    "error": tool_result.get("error"),
                })

                self.chat_message._publish_chat_realtime(
                    event_name="cf_streaming_update",
                    payload={
                        "message_id": self.chat_message.name,
                        "chat_id": self.chat_message.chat,
                        "message": f"[Tool] {function_name} executed",
                        "reasoning": "\n\n".join(all_reasoning_parts),
                        "status": "streaming",
                    },
                )

        frappe.logger("cognitive_folio").warning(
            "Tool-call chain reached max rounds (%s) for message %s; forcing final synthesis.",
            max_rounds,
            self.chat_message.name,
        )
        if not synthesis_nudge_sent:
            messages.append({
                "role": "system",
                "content": (
                    "You have used the maximum number of research rounds. "
                    "Write your final, complete answer now based on what you have gathered."
                ),
            })
        final_response = self.chat_message._create_non_stream_completion_with_retry(
            client=client,
            messages=messages,
            settings=settings,
            tools=None,
        )
        self.chat_message._accumulate_usage(aggregate_usage, getattr(final_response, "usage", None))
        if final_response.choices:
            final_choice = final_response.choices[0]
            final_message = final_choice.message
            final_content = getattr(final_message, "content", None) or ""
            final_reasoning = getattr(final_message, "reasoning_content", None) or ""
            if final_reasoning:
                all_reasoning_parts.append(final_reasoning)
            last_finish_reason = getattr(final_choice, "finish_reason", None)
            return final_content, "\n\n".join(all_reasoning_parts), last_finish_reason, aggregate_usage, tool_trace

        accumulated = " ".join(
            message.get("content", "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "assistant" and message.get("content")
        )
        return accumulated or "", "\n\n".join(all_reasoning_parts), last_finish_reason, aggregate_usage, tool_trace

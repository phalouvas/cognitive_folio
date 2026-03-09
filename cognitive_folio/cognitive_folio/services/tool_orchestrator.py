import json
import time

import frappe

from cognitive_folio.cognitive_folio.services.agent import (
    PlanExecutor,
    PlanGenerator,
    QueryAnalyzer,
    ToolRecommender,
)
from cognitive_folio.cognitive_folio.services.tooling import ToolComposer, ToolEffectivenessTracker, ToolMetricsStore, ToolSelfCorrector


class ToolOrchestrator:
    """Coordinates iterative tool-calling loops for chat completions."""

    REALTIME_WEB_MARKERS = (
        "weather",
        "temperature",
        "forecast",
        "rain",
        "wind",
        "humidity",
        "air quality",
    )
    CURRENT_TIME_MARKERS = (
        "now",
        "current",
        "currently",
        "right now",
        "today",
        "live",
        "latest",
    )

    def __init__(self, chat_message):
        self.chat_message = chat_message
        self.query_analyzer = QueryAnalyzer()
        self.tool_recommender = ToolRecommender()
        self.plan_generator = PlanGenerator()
        self.plan_executor = PlanExecutor()
        self.tool_composer = ToolComposer()
        self.tool_metrics_store = ToolMetricsStore()
        self.tool_self_corrector = ToolSelfCorrector()

    def run_tool_call_chain(self, client, messages, settings, chat, portfolio, security):
        tools = self.chat_message._get_tool_definitions(settings=settings)
        max_rounds = self.chat_message._get_max_tool_rounds(settings)
        max_tool_calls_per_round = self.chat_message._get_max_tool_calls_per_round(settings)
        tool_result_max_chars = self.chat_message._get_tool_result_max_chars(settings)
        settings_manager = self.chat_message._get_settings_manager(settings)
        planner_config = settings_manager.get_planner_config()
        tool_execution_config = settings_manager.get_tool_execution_config()
        effectiveness_tracker = ToolEffectivenessTracker()
        composition_context = {
            "last": None,
            "tools": {},
            "latest_user_message": "",
        }

        # Log simplified orchestration mode (conflict-duration and forced realtime removed)
        frappe.logger("cognitive_folio").info(
            "ToolOrchestrator: Simplified mode active (planner=%s, composition=%s, self_correction=%s)",
            bool(planner_config.get("enabled", True)),
            bool(tool_execution_config.get("composition_enabled", True)),
            bool(tool_execution_config.get("self_correction_enabled", True)),
        )

        analysis = {}
        plan = None
        recommendation = {"recommended_tools": []}
        if planner_config.get("enabled", True):
            analysis = self.query_analyzer.analyze(messages, config=planner_config)
            composition_context["latest_user_message"] = analysis.get("latest_user_message") or ""
            recommendation = self.tool_recommender.recommend(analysis, tools, config=planner_config)
            plan = self.plan_generator.generate(
                analysis=analysis,
                recommendation=recommendation,
                max_rounds=max_rounds,
                max_tool_calls_per_round=max_tool_calls_per_round,
                config=planner_config,
            )
            if planner_config.get("inject_system_plan", True):
                plan_message = self.plan_executor.build_system_plan_message(plan)
                if plan_message:
                    messages.append({"role": "system", "content": plan_message})



        current_datetime = frappe.utils.now_datetime()
        messages.append(
            {
                "role": "system",
                "content": (
                    "Current system datetime is "
                    f"{current_datetime.strftime('%Y-%m-%d %H:%M:%S %Z').strip()} "
                    f"(date: {current_datetime.strftime('%Y-%m-%d')}). "
                    "For time-sensitive questions, do not contradict this date and rely on tool evidence."
                ),
            }
        )

        effective_enforce_recommended_tools = self._effective_enforce_recommended_tools(planner_config, analysis)

        all_reasoning_parts = []
        tool_trace = []
        last_finish_reason = None
        aggregate_usage = {
            "tool_rounds": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "plan": plan,
            "planner": {
                "enabled": bool(planner_config.get("enabled", True)),
                "inject_system_plan": bool(planner_config.get("inject_system_plan", True)),
                "enforce_recommended_tools": bool(effective_enforce_recommended_tools),
            },
            "tool_execution": {
                "composition_enabled": bool(tool_execution_config.get("composition_enabled", True)),
                "self_correction_enabled": bool(tool_execution_config.get("self_correction_enabled", True)),
                "dynamic_registration_enabled": bool(tool_execution_config.get("dynamic_registration_enabled", True)),
                "max_corrections_per_call": int(tool_execution_config.get("max_corrections_per_call", 1)),
            },
        }
        synthesis_nudge_sent = False

        for round_index in range(1, max_rounds + 1):
            if self.plan_executor.should_inject_synthesis_nudge(round_index, max_rounds, synthesis_nudge_sent):
                synthesis_nudge_sent = True
                plan_steps = (plan or {}).get("steps") or []
                # Use the last 3 plan steps (the "synthesis" oriented ones) as mandatory section headers.
                # Explicitly named sections mean the model cannot satisfy the directive with a single
                # short paragraph — it must address each section, naturally producing comprehensive output.
                if plan_steps:
                    sections = "\n".join(f"## {s}" for s in plan_steps[-3:])
                    synthesis_directive = (
                        "Research phase complete. FINAL SYNTHESIS REQUIRED — "
                        "no further tool calls will be processed.\n\n"
                        "You MUST produce ALL of the following sections using the data gathered above. "
                        "Each section must be substantive (3+ sentences with specific data/numbers from tools).\n\n"
                        f"{sections}\n\n"
                        "Do NOT skip any section. Do NOT output raw parameter values. "
                        "Begin with the first section heading immediately."
                    )
                else:
                    synthesis_directive = (
                        "Research phase complete. FINAL SYNTHESIS REQUIRED — "
                        "no further tool calls will be processed from this point. "
                        "You MUST now write a thorough, comprehensive response (minimum 500 words) "
                        "using ALL the data gathered from the tool results above. "
                        "Structure your response with ## headings, specific numbers/data from tools, "
                        "and bullet points for key findings. "
                        "Address EVERY aspect of the user's question in detail. "
                        "Do NOT output raw parameter values or tool argument lists. "
                        "Begin writing the complete detailed analysis immediately."
                    )
                messages.append({"role": "system", "content": synthesis_directive})

            active_tools = self.plan_executor.active_tools_for_round(
                tools,
                round_index,
                max_rounds,
                recommended_tools=recommendation.get("recommended_tools") if isinstance(recommendation, dict) else None,
                enforce_recommended=bool(effective_enforce_recommended_tools),
            )
            # Enforce synthesis: once the synthesis directive has fired, suppress all tools so
            # the model cannot defer to another tool call instead of writing the final answer.
            if synthesis_nudge_sent:
                active_tools = None
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

                # For any synthesis round where tools were actually used, always run the
                # expansion pass — not just when content is thin.  The first synthesis call
                # reliably produces a structured skeleton; the expansion pass deepens each
                # section with specific data, numbers, and recommendations.  This is the
                # standard quality path for complex multi-tool queries.
                # For simple queries with no tool data, fall through to the weak-content check.
                should_expand = synthesis_nudge_sent and bool(tool_trace)

                nudge_min_chars = max(800, round_index * 500) if synthesis_nudge_sent else None
                if should_expand or (
                    (synthesis_nudge_sent or tool_trace) and self._is_weak_synthesis_content(
                        assistant_content, round_index, min_chars=nudge_min_chars
                    )
                ):
                    frappe.logger("cognitive_folio").info(
                        "Expanding synthesis at round %s (len=%s, tools_used=%s).",
                        round_index,
                        len(assistant_content or ""),
                        len(tool_trace),
                    )
                    forced = self._force_synthesis_response(
                        client=client,
                        messages=messages,
                        settings=settings,
                        aggregate_usage=aggregate_usage,
                        prior_content=assistant_content,
                    )
                    if forced:
                        forced_content, forced_reasoning, forced_finish = forced
                        if forced_reasoning:
                            all_reasoning_parts.append(forced_reasoning)
                        aggregate_usage["tool_metrics"] = effectiveness_tracker.as_dict()
                        aggregate_usage["tool_metrics_store"] = self._persist_tool_metrics(aggregate_usage)
                        return forced_content, "\n\n".join(all_reasoning_parts), forced_finish, aggregate_usage, tool_trace

                if self.chat_message._content_looks_like_dsml(assistant_content):
                    messages.append(self.chat_message._build_assistant_message_dict("", reasoning_content, []))
                    break
                messages.append(self.chat_message._build_assistant_message_dict(assistant_content, reasoning_content, []))
                aggregate_usage["tool_metrics"] = effectiveness_tracker.as_dict()
                aggregate_usage["tool_metrics_store"] = self._persist_tool_metrics(aggregate_usage)
                return assistant_content, "\n\n".join(all_reasoning_parts), last_finish_reason, aggregate_usage, tool_trace

            tool_calls_to_execute = self.plan_executor.select_tool_calls(
                tool_calls=tool_calls,
                max_per_round=max_tool_calls_per_round,
                recommended_tools=recommendation.get("recommended_tools") if isinstance(recommendation, dict) else None,
                enforce_recommended=bool(effective_enforce_recommended_tools),
            )

            assistant_tool_calls = []
            for tool_call in tool_calls_to_execute:
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

            for tool_call in tool_calls_to_execute:
                call_started = time.time()
                call_id = getattr(tool_call, "id", None)
                function_obj = getattr(tool_call, "function", None)
                function_name = getattr(function_obj, "name", "") if function_obj else ""
                arguments_raw = getattr(function_obj, "arguments", "{}") if function_obj else "{}"

                if tool_execution_config.get("composition_enabled", True):
                    arguments_raw = self.tool_composer.compose_arguments_raw(arguments_raw, composition_context)

                tool_result = self.chat_message._execute_tool_call(
                    function_name=function_name,
                    arguments_raw=arguments_raw,
                    chat=chat,
                    portfolio=portfolio,
                    security=security,
                    dynamic_registration_enabled=bool(tool_execution_config.get("dynamic_registration_enabled", True)),
                )

                retried = False
                corrections_left = int(tool_execution_config.get("max_corrections_per_call", 1))
                while (
                    not tool_result.get("ok", False)
                    and tool_execution_config.get("self_correction_enabled", True)
                    and corrections_left > 0
                ):
                    corrected_args = self.tool_self_corrector.build_retry_arguments(
                        function_name=function_name,
                        arguments_raw=arguments_raw,
                        tool_result=tool_result,
                        context=composition_context,
                    )
                    if not corrected_args:
                        break
                    retried = True
                    arguments_raw = json.dumps(corrected_args, ensure_ascii=False, default=str)
                    tool_result = self.chat_message._execute_tool_call(
                        function_name=function_name,
                        arguments_raw=arguments_raw,
                        chat=chat,
                        portfolio=portfolio,
                        security=security,
                        dynamic_registration_enabled=bool(tool_execution_config.get("dynamic_registration_enabled", True)),
                    )
                    corrections_left -= 1

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
                    "retried": retried,
                    "args": tool_result.get("args", {}),
                    "error_code": tool_result.get("error_code"),
                    "error": tool_result.get("error"),
                })

                last_trace = tool_trace[-1]
                effectiveness_tracker.record(
                    tool_name=function_name,
                    ok=bool(last_trace.get("ok", False)),
                    duration_ms=float(last_trace.get("duration_ms", 0) or 0),
                    retried=bool(last_trace.get("retried", False)),
                )

                composition_context["last"] = tool_result
                composition_context.setdefault("tools", {}).setdefault(function_name, []).append(tool_result)

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

            # Always expand when tools were used — same quality guarantee as the in-loop path.
            if bool(tool_trace) or self._is_weak_synthesis_content(final_content, max_rounds):
                frappe.logger("cognitive_folio").info(
                    "Expanding post-loop synthesis for message %s (len=%s, tools_used=%s).",
                    self.chat_message.name,
                    len(final_content),
                    len(tool_trace),
                )
                forced = self._force_synthesis_response(
                    client=client,
                    messages=messages,
                    settings=settings,
                    aggregate_usage=aggregate_usage,
                    prior_content=final_content,
                )
                if forced:
                    forced_content, forced_reasoning, forced_finish = forced
                    if forced_reasoning:
                        all_reasoning_parts.append(forced_reasoning)
                    final_content = forced_content or final_content
                    last_finish_reason = forced_finish or last_finish_reason

            aggregate_usage["tool_metrics"] = effectiveness_tracker.as_dict()
            aggregate_usage["tool_metrics_store"] = self._persist_tool_metrics(aggregate_usage)
            return final_content, "\n\n".join(all_reasoning_parts), last_finish_reason, aggregate_usage, tool_trace

        accumulated = " ".join(
            message.get("content", "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "assistant" and message.get("content")
        )
        aggregate_usage["tool_metrics"] = effectiveness_tracker.as_dict()
        aggregate_usage["tool_metrics_store"] = self._persist_tool_metrics(aggregate_usage)
        return accumulated or "", "\n\n".join(all_reasoning_parts), last_finish_reason, aggregate_usage, tool_trace

    def _is_weak_synthesis_content(self, content, tool_rounds, min_chars=None):
        """Return True if content is too thin to be a real synthesis after multi-round data gathering.

        Args:
            min_chars: explicit minimum character count; defaults to max(200, tool_rounds * 400).
                       Callers that explicitly requested synthesis should pass a higher value.
        """
        if not content:
            return True
        stripped = content.strip()
        # Short content after research rounds is likely weak/incomplete.
        # Default threshold scales with the number of research rounds so that a
        # 3-round deep-research query requires proportionally more output than a simple 1-round ask.
        effective_min = min_chars if min_chars is not None else max(200, int(tool_rounds or 0) * 400)
        if len(stripped) < effective_min:
            return True
        # Detect leaked tool-call argument artifacts (content looks like raw query params rather
        # than a structured answer).  Only flag these when tools were actually used.
        if int(tool_rounds or 0) >= 1 and len(stripped) < 400:
            has_structure = (
                "#" in stripped
                or "**" in stripped
                or "\n-" in stripped
                or "\n*" in stripped
                or "\n1." in stripped
            )
            opener_is_planning = (
                stripped.lower().startswith("let me")
                or stripped.lower().startswith("i need to")
                or stripped.lower().startswith("searching for")
            )
            if opener_is_planning and not has_structure:
                return True
        return False

    def _force_synthesis_response(self, client, messages, settings, aggregate_usage, prior_content=None):
        """Force a comprehensive synthesis completion when the model produced a weak/thin response.

        Strategy: if a thin prior response exists, append it as an assistant turn so the model
        sees it as its own incomplete work, then use an expansion directive.  This is far more
        reliable than a fresh "write more" system directive because the model is asked to
        *continue/deepen* what it already started rather than produce new content from scratch.

        For deepseek-reasoner, falls back to deepseek-chat to avoid tool-arg artifact leakage.

        Returns (content, reasoning_content, finish_reason) on success, or None on failure.
        """
        if prior_content and prior_content.strip():
            # Put the thin output back as an assistant message so the model treats it as its
            # own prior work that needs to be continued and expanded.
            messages.append({
                "role": "assistant",
                "content": prior_content,
            })
            messages.append({
                "role": "user",
                "content": (
                    "Your analysis above is incomplete. Please expand it into a comprehensive report. "
                    "For each section already started, add 2-3 more detailed paragraphs with specific "
                    "data, numbers, and actionable insights from the research results. "
                    "Add any important sections that are missing. "
                    "Do not repeat what is already written — only add the missing depth and detail."
                ),
            })
        else:
            messages.append({
                "role": "system",
                "content": (
                    "CRITICAL: Tool calls are permanently disabled. "
                    "Write the complete, structured analysis NOW using only the data already "
                    "gathered in this conversation. "
                    "Your response MUST be comprehensive (minimum 500 words) with ## headings, "
                    "bullet points, and specific numbers/data from the tool results. "
                    "Do NOT output function argument values. "
                    "Begin immediately with the analysis content."
                ),
            })

        is_reasoner = self.chat_message._is_reasoner_model(
            getattr(self.chat_message, "model", ""), settings
        )
        resp = None
        if is_reasoner:
            # deepseek-reasoner commits to tool-call plans during its thinking phase and
            # leaks those argument values into content when tools are then unavailable.
            # Use deepseek-chat for a clean synthesis pass that avoids this pattern.
            try:
                chat_max_tokens = max(int(getattr(settings, "chat_default_max_tokens", None) or 4000), 8192)
                # Strip reasoning_content from history — deepseek-chat rejects it as an
                # unknown field and it adds no value for the chat model synthesis pass.
                clean_messages = [
                    {k: v for k, v in m.items() if k != "reasoning_content"}
                    if isinstance(m, dict) else m
                    for m in messages
                ]
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=clean_messages,
                    stream=False,
                    max_tokens=chat_max_tokens,
                )
                aggregate_usage.setdefault("tool_execution", {})["synthesis_fallback_model"] = "deepseek-chat"
            except Exception as exc:  # noqa: BLE001
                frappe.logger("cognitive_folio").warning(
                    "deepseek-chat synthesis fallback failed (%s); using primary model.", exc
                )

        if resp is None:
            resp = self.chat_message._create_non_stream_completion_with_retry(
                client=client,
                messages=messages,
                settings=settings,
                tools=None,
            )

        self.chat_message._accumulate_usage(aggregate_usage, getattr(resp, "usage", None))
        if not getattr(resp, "choices", None):
            return None

        choice = resp.choices[0]
        msg = choice.message
        forced_content = getattr(msg, "content", None) or ""
        forced_reasoning = getattr(msg, "reasoning_content", None) or ""
        forced_finish = getattr(choice, "finish_reason", None)

        # If the first forced synthesis is still weak, append it and ask for expansion once more.
        tool_rounds = aggregate_usage.get("tool_rounds", 0)
        if self._is_weak_synthesis_content(forced_content, tool_rounds):
            frappe.logger("cognitive_folio").warning(
                "First forced synthesis still weak (len=%s); attempting one final retry.",
                len(forced_content),
            )
            if forced_content and forced_content.strip():
                messages.append({"role": "assistant", "content": forced_content})
                messages.append({
                    "role": "user",
                    "content": (
                        "This response is still too brief. "
                        "Continue the analysis with substantially more detail: deeper context, "
                        "more specific data points, portfolio implications, and concrete recommendations. "
                        "Expand each section significantly."
                    ),
                })
            else:
                messages.append({
                    "role": "system",
                    "content": (
                        "FINAL ATTEMPT: Your previous response was still insufficient. "
                        "You MUST produce a complete, well-structured analysis NOW. "
                        "Start immediately with a \'##\' heading, then write detailed paragraphs. "
                        "Do NOT reference tool arguments or parameter values."
                    ),
                })
            retry_resp = self.chat_message._create_non_stream_completion_with_retry(
                client=client,
                messages=messages,
                settings=settings,
                tools=None,
            )
            self.chat_message._accumulate_usage(aggregate_usage, getattr(retry_resp, "usage", None))
            if getattr(retry_resp, "choices", None):
                retry_choice = retry_resp.choices[0]
                retry_msg = retry_choice.message
                retry_content = getattr(retry_msg, "content", None) or ""
                if retry_content:
                    return (
                        retry_content,
                        getattr(retry_msg, "reasoning_content", None) or "",
                        getattr(retry_choice, "finish_reason", None),
                    )

        return forced_content, forced_reasoning, forced_finish

    def _latest_user_message(self, messages):
        for message in reversed(messages or []):
            if isinstance(message, dict) and message.get("role") == "user":
                return (message.get("content") or "").strip()
        return ""

    def _persist_tool_metrics(self, aggregate_usage):
        metrics = (aggregate_usage or {}).get("tool_metrics") or {}
        plan = (aggregate_usage or {}).get("plan") or {}
        context = {
            "model": getattr(self.chat_message, "model", None),
            "intent": plan.get("intent") if isinstance(plan, dict) else None,
            "chat": getattr(self.chat_message, "chat", None),
            "message": getattr(self.chat_message, "name", None),
        }
        return self.tool_metrics_store.persist_daily_rollups(metrics, context=context)

    def _effective_enforce_recommended_tools(self, planner_config, analysis):
        if bool((planner_config or {}).get("enforce_recommended_tools", False)):
            return True

        intent = (analysis or {}).get("intent") or ""
        scores = (analysis or {}).get("scores") or {}
        financial_hits = int(scores.get("financial_hits", 0) or 0)
        return intent == "general_research" and financial_hits == 0

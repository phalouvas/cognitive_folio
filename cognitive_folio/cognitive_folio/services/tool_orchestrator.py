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
    CONFLICT_MARKERS = (
        "war",
        "conflict",
        "military",
        "iran",
        "israel",
        "usa",
        "united states",
    )
    DURATION_MARKERS = (
        "how long",
        "duration",
        "last",
        "estimate",
        "timeline",
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

        conflict_duration_mode = self._is_conflict_duration_query(composition_context.get("latest_user_message") or "")
        if conflict_duration_mode:
            max_rounds = min(max_rounds, 4)
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "For conflict-duration questions with uncertain or sparse evidence: "
                        "do not stop at saying evidence is limited. Provide a concise scenario estimate "
                        "(best/base/worst case duration ranges), key drivers, and a confidence level. "
                        "Clearly separate verified facts from assumptions."
                    ),
                }
            )

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
                "forced_realtime_web_search": False,
                "conflict_duration_mode": bool(conflict_duration_mode),
                "conflict_duration_rewrite": False,
            },
        }
        synthesis_nudge_sent = False
        conflict_rewrite_done = False

        for round_index in range(1, max_rounds + 1):
            if self.plan_executor.should_inject_synthesis_nudge(round_index, max_rounds, synthesis_nudge_sent):
                synthesis_nudge_sent = True
                messages.append({
                    "role": "system",
                    "content": (
                        "Research phase complete. FINAL SYNTHESIS REQUIRED — "
                        "no further tool calls will be processed from this point. "
                        "You MUST now write a complete, structured response using all the data gathered above. "
                        "Do NOT output raw parameter values or tool argument lists. "
                        "Produce the full formatted analysis addressing all user requirements."
                    ),
                })
            elif round_index == max_rounds:
                # Safety net: repeat directive if we somehow reach the absolute last round
                messages.append({
                    "role": "system",
                    "content": (
                        "FINAL ROUND — No further tool calls are available. "
                        "You MUST now write a complete, structured response using the data gathered above. "
                        "Do NOT output raw values or parameter lists. "
                        "Produce the full formatted analysis addressing all user requirements."
                    ),
                })

            active_tools = self.plan_executor.active_tools_for_round(
                tools,
                round_index,
                max_rounds,
                recommended_tools=recommendation.get("recommended_tools") if isinstance(recommendation, dict) else None,
                enforce_recommended=bool(effective_enforce_recommended_tools),
            )
            # Enforce synthesis: once the synthesis directive has fired, suppress all tools so
            # the model cannot defer to another tool call instead of writing the final answer.
            # (The round_index > 1 guard protects the edge case where max_rounds <= 2.)
            if synthesis_nudge_sent and round_index > 1:
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
                latest_user_message = composition_context.get("latest_user_message") or self._latest_user_message(messages)
                if self._should_force_realtime_web_search(
                    latest_user_message=latest_user_message,
                    analysis=analysis,
                    recommendation=recommendation,
                    tool_trace=tool_trace,
                    round_index=round_index,
                    max_rounds=max_rounds,
                ):
                    self._inject_forced_web_search_context(
                        messages=messages,
                        latest_user_message=latest_user_message,
                        tool_result_max_chars=tool_result_max_chars,
                        chat=chat,
                        portfolio=portfolio,
                        security=security,
                        round_index=round_index,
                        tool_trace=tool_trace,
                        effectiveness_tracker=effectiveness_tracker,
                    )
                    aggregate_usage["tool_execution"]["forced_realtime_web_search"] = True
                    continue

                if conflict_duration_mode and tool_trace and not conflict_rewrite_done:
                    conflict_rewrite_done = True
                    rewrite_response, rewrite_reasoning, rewrite_finish = self._run_conflict_duration_rewrite(
                        client=client,
                        messages=messages,
                        settings=settings,
                        draft_content=assistant_content,
                        draft_reasoning=reasoning_content,
                        tool_trace=tool_trace,
                        aggregate_usage=aggregate_usage,
                    )
                    aggregate_usage["tool_execution"]["conflict_duration_rewrite"] = True
                    if rewrite_reasoning:
                        all_reasoning_parts.append(rewrite_reasoning)
                    aggregate_usage["tool_metrics"] = effectiveness_tracker.as_dict()
                    aggregate_usage["tool_metrics_store"] = self._persist_tool_metrics(aggregate_usage)
                    return rewrite_response, "\n\n".join(all_reasoning_parts), rewrite_finish, aggregate_usage, tool_trace

                if synthesis_nudge_sent and self._is_weak_synthesis_content(assistant_content, round_index):
                    frappe.logger("cognitive_folio").warning(
                        "Weak synthesis at round %s (len=%s); forcing synthesis pass.",
                        round_index,
                        len(assistant_content or ""),
                    )
                    forced = self._force_synthesis_response(
                        client=client,
                        messages=messages,
                        settings=settings,
                        aggregate_usage=aggregate_usage,
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

            if self._is_weak_synthesis_content(final_content, max_rounds):
                frappe.logger("cognitive_folio").warning(
                    "Weak forced synthesis for message %s (len=%s); forcing synthesis pass.",
                    self.chat_message.name,
                    len(final_content),
                )
                forced = self._force_synthesis_response(
                    client=client,
                    messages=messages,
                    settings=settings,
                    aggregate_usage=aggregate_usage,
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

    def _is_weak_synthesis_content(self, content, tool_rounds):
        """Return True if content is too thin to be a real synthesis after multi-round data gathering."""
        if not content:
            return True
        return len(content.strip()) < 200 and int(tool_rounds or 0) >= 2

    def _force_synthesis_response(self, client, messages, settings, aggregate_usage):
        """Force a clean synthesis completion when the model produced a weak/garbage response.

        Appends a CRITICAL synthesis directive WITHOUT first appending the garbage content
        (which would confuse the model into repeating it).  For deepseek-reasoner, falls back
        to deepseek-chat so tool-arg artifacts from the reasoner's thinking phase are bypassed.

        Returns (content, reasoning_content, finish_reason) on success, or None on failure.
        """
        messages.append({
            "role": "system",
            "content": (
                "CRITICAL: Tool calls are permanently disabled. "
                "Write the complete, structured analysis now using only the data already "
                "gathered in this conversation. "
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
                chat_max_tokens = int(getattr(settings, "chat_default_max_tokens", None) or 4000)
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
        return (
            getattr(msg, "content", None) or "",
            getattr(msg, "reasoning_content", None) or "",
            getattr(choice, "finish_reason", None),
        )

    def _latest_user_message(self, messages):
        for message in reversed(messages or []):
            if isinstance(message, dict) and message.get("role") == "user":
                return (message.get("content") or "").strip()
        return ""

    def _is_realtime_external_query(self, latest_user_message):
        lowered = str(latest_user_message or "").lower()
        if not lowered:
            return False

        has_realtime = any(marker in lowered for marker in self.CURRENT_TIME_MARKERS)
        has_weather = any(marker in lowered for marker in self.REALTIME_WEB_MARKERS)
        return has_weather and (has_realtime or "weather" in lowered)

    def _should_force_realtime_web_search(self, latest_user_message, analysis, recommendation, tool_trace, round_index, max_rounds):
        if not bool(getattr(self.chat_message, "web_search", False)):
            return False
        if tool_trace:
            return False
        if round_index >= max_rounds:
            return False

        lowered = str(latest_user_message or "").lower()
        if not lowered:
            return False

        if self._is_realtime_external_query(lowered):
            return True

        intent = (analysis or {}).get("intent") or ""
        recommended_tools = set((recommendation or {}).get("recommended_tools") or [])
        looks_realtime = any(marker in lowered for marker in self.CURRENT_TIME_MARKERS)
        return intent == "general_research" and looks_realtime and "web_search" in recommended_tools

    def _inject_forced_web_search_context(
        self,
        messages,
        latest_user_message,
        tool_result_max_chars,
        chat,
        portfolio,
        security,
        round_index,
        tool_trace,
        effectiveness_tracker,
    ):
        call_started = time.time()
        forced_args = {
            "query": latest_user_message,
            "max_results": 5,
            "provider": "auto",
            "date_range": "day",
            "result_type": "snippets",
        }

        tool_result = self.chat_message._execute_tool_call(
            function_name="web_search",
            arguments_raw=json.dumps(forced_args, ensure_ascii=False, default=str),
            chat=chat,
            portfolio=portfolio,
            security=security,
            dynamic_registration_enabled=True,
        )

        result_content = json.dumps(tool_result, ensure_ascii=False, default=str)
        if len(result_content) > tool_result_max_chars:
            result_content = result_content[:tool_result_max_chars] + "..."

        messages.append(
            {
                "role": "system",
                "content": (
                    "Realtime search fallback was executed for the latest user query. "
                    "Use these results directly and do not claim you lack realtime lookup capability.\n"
                    f"{result_content}"
                ),
            }
        )

        ok = bool((tool_result or {}).get("ok", False))
        duration_ms = round((time.time() - call_started) * 1000, 2)
        tool_trace.append(
            {
                "round": round_index,
                "tool": "web_search",
                "call_id": f"forced_web_search_round_{round_index}",
                "ok": ok,
                "duration_ms": duration_ms,
                "retried": False,
                "forced": True,
                "args": forced_args,
                "error_code": (tool_result or {}).get("error_code"),
                "error": (tool_result or {}).get("error"),
            }
        )

        effectiveness_tracker.record(
            tool_name="web_search",
            ok=ok,
            duration_ms=duration_ms,
            retried=False,
        )

        self.chat_message._publish_chat_realtime(
            event_name="cf_streaming_update",
            payload={
                "message_id": self.chat_message.name,
                "chat_id": self.chat_message.chat,
                "message": "[Tool] web_search executed (forced realtime fallback)",
                "reasoning": "",
                "status": "streaming",
            },
        )

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

    def _is_conflict_duration_query(self, latest_user_message):
        lowered = str(latest_user_message or "").lower()
        if not lowered:
            return False

        has_conflict = any(marker in lowered for marker in self.CONFLICT_MARKERS)
        has_duration = any(marker in lowered for marker in self.DURATION_MARKERS)
        return has_conflict and has_duration

    def _run_conflict_duration_rewrite(self, client, messages, settings, draft_content, draft_reasoning, tool_trace, aggregate_usage):
        searched_queries = []
        for item in tool_trace or []:
            args = (item or {}).get("args") or {}
            query = str(args.get("query") or "").strip()
            if query:
                searched_queries.append(query)
        searched_queries = searched_queries[:5]

        evidence_prompt = (
            "Rewrite the previous answer using these strict rules:\n"
            "1) Do NOT claim definitively that an event does not exist.\n"
            "2) Use wording: 'I could not verify from retrieved sources'.\n"
            "3) Keep verified findings and hypothetical scenario estimates clearly separated.\n"
            "4) Provide duration ranges as Best/Base/Worst case only if user asked for estimate.\n"
            "5) Confidence must be one of: low, medium, high (never N/A).\n"
            "6) Keep concise and non-repetitive.\n"
            f"Tool calls executed: {len(tool_trace or [])}.\n"
            f"Queries searched: {searched_queries}."
        )

        rewrite_messages = list(messages or [])
        rewrite_messages.append(
            {
                "role": "assistant",
                "content": draft_content or "",
                "reasoning_content": draft_reasoning or "",
            }
        )
        rewrite_messages.append({"role": "system", "content": evidence_prompt})

        rewrite_completion = self.chat_message._create_non_stream_completion_with_retry(
            client=client,
            messages=rewrite_messages,
            settings=settings,
            tools=None,
        )
        self.chat_message._accumulate_usage(aggregate_usage, getattr(rewrite_completion, "usage", None))

        if not getattr(rewrite_completion, "choices", None):
            return draft_content or "", draft_reasoning or "", "stop"

        rewrite_choice = rewrite_completion.choices[0]
        rewrite_message = rewrite_choice.message
        return (
            getattr(rewrite_message, "content", None) or draft_content or "",
            getattr(rewrite_message, "reasoning_content", None) or "",
            getattr(rewrite_choice, "finish_reason", None) or "stop",
        )

class PlanExecutor:
    """Translate plan into execution-time orchestration decisions."""

    def build_system_plan_message(self, plan):
        if not isinstance(plan, dict):
            return ""

        intent = plan.get("intent") or "general_assistance"
        tools = plan.get("recommended_tools") or []
        steps = plan.get("steps") or []

        tool_text = ", ".join(tools) if tools else "none"
        step_lines = "\n".join(f"- {step}" for step in steps)

        return (
            "Execution plan:\n"
            f"Intent: {intent}\n"
            f"Preferred tools: {tool_text}\n"
            "Plan steps:\n"
            f"{step_lines}\n"
            "Use tool calls as needed, then provide a concise final synthesis."
        )

    def should_inject_synthesis_nudge(self, round_index, max_rounds, synthesis_nudge_sent):
        return not synthesis_nudge_sent and round_index == max_rounds

    def active_tools_for_round(self, tools, round_index, max_rounds, recommended_tools=None, enforce_recommended=False):
        if round_index == max_rounds:
            return None

        if not enforce_recommended:
            return tools

        preferred_names = set(recommended_tools or [])
        if not preferred_names:
            return []

        filtered = []
        for item in tools or []:
            function_obj = (item or {}).get("function") if isinstance(item, dict) else None
            name = (function_obj or {}).get("name") if isinstance(function_obj, dict) else None
            if name in preferred_names:
                filtered.append(item)
        return filtered

    def select_tool_calls(self, tool_calls, max_per_round, recommended_tools=None, enforce_recommended=False):
        ordered = list(tool_calls or [])
        if not ordered:
            return []

        preferred_names = set(recommended_tools or [])
        if not preferred_names:
            return ordered[:max_per_round]

        preferred = []
        other = []
        for tool_call in ordered:
            function_obj = getattr(tool_call, "function", None)
            name = getattr(function_obj, "name", "") if function_obj else ""
            if name in preferred_names:
                preferred.append(tool_call)
            elif not enforce_recommended:
                other.append(tool_call)

        selected = preferred if enforce_recommended else (preferred + other)
        if not selected and not enforce_recommended:
            selected = ordered
        return selected[:max_per_round]

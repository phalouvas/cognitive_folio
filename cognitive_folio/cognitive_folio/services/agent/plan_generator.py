class PlanGenerator:
    """Generate a lightweight plan before tool-chain execution."""

    def generate(self, analysis, recommendation, max_rounds, max_tool_calls_per_round, config=None):
        config = config or {}
        analysis = analysis or {}
        recommendation = recommendation or {}

        intent = analysis.get("intent") or "general_assistance"
        complexity = analysis.get("complexity") or "low"
        recommended_tools = recommendation.get("recommended_tools") or []

        steps = [
            "Understand user objective",
            "Collect data with recommended tools",
            "Synthesize evidence",
            "Produce final answer",
        ]

        if complexity == "high":
            steps.insert(2, "Cross-check findings across multiple tool outputs")

        max_plan_steps = int(config.get("max_plan_steps", 6))
        if max_plan_steps > 0:
            steps = steps[:max_plan_steps]

        return {
            "intent": intent,
            "complexity": complexity,
            "recommended_tools": recommended_tools,
            "max_rounds": int(max_rounds),
            "max_tool_calls_per_round": int(max_tool_calls_per_round),
            "steps": steps,
        }

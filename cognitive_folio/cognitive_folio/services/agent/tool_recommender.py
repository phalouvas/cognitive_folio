class ToolRecommender:
    """Recommend tools based on query analysis and available tool definitions."""

    INTENT_TOOL_MAP = {
        "financial_research": ["search_financial", "web_search", "get_security_snapshot", "get_portfolio_holdings"],
        "portfolio_analysis": ["get_portfolio_holdings", "search_financial", "web_search"],
        "security_analysis": ["get_security_snapshot", "get_latest_security_news", "search_financial", "web_search"],
        "general_research": ["web_search", "fetch_url_content"],
        "general_assistance": [],
    }

    def recommend(self, analysis, tools, config=None):
        config = config or {}
        available_tool_names = []
        for item in tools or []:
            function_obj = (item or {}).get("function") or {}
            name = function_obj.get("name")
            if name:
                available_tool_names.append(name)

        intent = (analysis or {}).get("intent") or "general_assistance"
        intent_tool_map = config.get("intent_tool_map") or self.INTENT_TOOL_MAP
        max_recommended_tools = int(config.get("max_recommended_tools", 4))
        recommended = list(intent_tool_map.get(intent, []))
        filtered = [tool_name for tool_name in recommended if tool_name in available_tool_names][:max_recommended_tools]

        if not filtered:
            requires_tools = bool((analysis or {}).get("requires_tools", False))
            if requires_tools:
                fallback = ["web_search", "fetch_url_content"]
                filtered = [tool_name for tool_name in fallback if tool_name in available_tool_names][:max_recommended_tools]
            else:
                filtered = []

        return {
            "recommended_tools": filtered,
            "available_tools": available_tool_names,
            "intent": intent,
        }

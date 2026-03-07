class QueryAnalyzer:
    """Analyze the latest user message for intent and complexity."""

    _FINANCIAL_MARKERS = (
        "stock",
        "portfolio",
        "earnings",
        "10-k",
        "10-q",
        "sec",
        "valuation",
        "ticker",
        "dividend",
        "balance sheet",
    )

    _RESEARCH_MARKERS = (
        "search",
        "latest",
        "news",
        "recent",
        "find",
        "sources",
        "web",
        "compare",
    )

    def analyze(self, messages, config=None):
        config = config or {}
        latest_user_message = ""
        for message in reversed(messages or []):
            if isinstance(message, dict) and message.get("role") == "user":
                latest_user_message = (message.get("content") or "").strip()
                break

        lowered = latest_user_message.lower()
        financial_markers = self._resolve_markers(config.get("financial_markers"), self._FINANCIAL_MARKERS)
        research_markers = self._resolve_markers(config.get("research_markers"), self._RESEARCH_MARKERS)
        financial_hits = sum(1 for marker in financial_markers if marker in lowered)
        research_hits = sum(1 for marker in research_markers if marker in lowered)

        if financial_hits >= 2:
            intent = "financial_research"
        elif "portfolio" in lowered:
            intent = "portfolio_analysis"
        elif "security" in lowered or "ticker" in lowered:
            intent = "security_analysis"
        elif research_hits > 0:
            intent = "general_research"
        else:
            intent = "general_assistance"

        complexity_score = 0
        if len(latest_user_message) > int(config.get("long_query_chars", 450)):
            complexity_score += 1
        if " and " in lowered or "compare" in lowered:
            complexity_score += 1
        if research_hits >= 2:
            complexity_score += 1
        if financial_hits >= 2:
            complexity_score += 1

        high_threshold = int(config.get("complexity_high_threshold", 3))
        medium_threshold = int(config.get("complexity_medium_threshold", 1))
        complexity = "high" if complexity_score >= high_threshold else "medium" if complexity_score >= medium_threshold else "low"

        return {
            "intent": intent,
            "complexity": complexity,
            "requires_tools": intent != "general_assistance" or complexity != "low",
            "latest_user_message": latest_user_message,
            "scores": {
                "financial_hits": financial_hits,
                "research_hits": research_hits,
                "complexity_score": complexity_score,
            },
        }

    def _resolve_markers(self, override_markers, default_markers):
        if not override_markers:
            return default_markers

        normalized = []
        for marker in override_markers:
            text = str(marker).strip().lower()
            if text:
                normalized.append(text)
        return tuple(normalized) or default_markers

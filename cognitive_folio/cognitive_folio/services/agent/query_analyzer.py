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

    _GEOPOLITICAL_MARKERS = (
        "war",
        "conflict",
        "iran",
        "israel",
        "usa",
        "united states",
        "ceasefire",
        "military",
        "geopolitical",
        "sanctions",
    )

    _TEMPORAL_MARKERS = (
        "now",
        "current",
        "currently",
        "today",
        "this week",
        "this month",
        "started",
        "since",
        "estimate",
        "how long",
        "duration",
        "2024",
        "2025",
        "2026",
        "2027",
    )

    _DISCOVERY_MARKERS = (
        "discover",
        "find stocks",
        "find me stocks",
        "find me companies",
        "search for companies",
        "search for stocks",
        "investment ideas",
        "good candidates",
        "purchase based on financials",
        "screen stocks",
        "filter stocks",
        "stocks with",
        "companies with",
        "high dividend",
        "low pe",
        "pe under",
        "pe below",
        "undervalued",
        "growth stocks",
        "value stocks",
        "investment opportunities",
        "investment candidates",
        "stock screening",
        "stock filter",
        "financial screening",
        "financial filter",
        "p/e ratio",
        "price to earnings",
        "dividend yield",
        "market cap",
        "with p/e",
        "p/e",
        "dividend",
        "financial criteria",
        "screening criteria",
        "filter by",
        "screen by",
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
        geopolitical_markers = self._resolve_markers(config.get("geopolitical_markers"), self._GEOPOLITICAL_MARKERS)
        temporal_markers = self._resolve_markers(config.get("temporal_markers"), self._TEMPORAL_MARKERS)
        discovery_markers = self._resolve_markers(config.get("discovery_markers"), self._DISCOVERY_MARKERS)
        financial_hits = sum(1 for marker in financial_markers if marker in lowered)
        research_hits = sum(1 for marker in research_markers if marker in lowered)
        geopolitical_hits = sum(1 for marker in geopolitical_markers if marker in lowered)
        temporal_hits = sum(1 for marker in temporal_markers if marker in lowered)
        discovery_hits = sum(1 for marker in discovery_markers if marker in lowered)

        if discovery_hits >= 2:
            intent = "securities_discovery"
        elif financial_hits >= 2:
            intent = "financial_research"
        elif "portfolio" in lowered:
            intent = "portfolio_analysis"
        elif "security" in lowered or "ticker" in lowered:
            intent = "security_analysis"
        elif research_hits > 0 or (geopolitical_hits > 0 and temporal_hits > 0):
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
        if geopolitical_hits >= 2:
            complexity_score += 1
        if temporal_hits >= 2:
            complexity_score += 1
        if discovery_hits >= 2:
            complexity_score += 1

        high_threshold = int(config.get("complexity_high_threshold", 3))
        medium_threshold = int(config.get("complexity_medium_threshold", 1))
        complexity = "high" if complexity_score >= high_threshold else "medium" if complexity_score >= medium_threshold else "low"

        requires_tools = intent != "general_assistance" or complexity != "low"
        if geopolitical_hits > 0 and temporal_hits > 0:
            requires_tools = True

        return {
            "intent": intent,
            "complexity": complexity,
            "requires_tools": requires_tools,
            "latest_user_message": latest_user_message,
            "scores": {
                "financial_hits": financial_hits,
                "research_hits": research_hits,
                "geopolitical_hits": geopolitical_hits,
                "temporal_hits": temporal_hits,
                "discovery_hits": discovery_hits,
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

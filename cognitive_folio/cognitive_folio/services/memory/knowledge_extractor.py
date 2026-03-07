import re


class KnowledgeExtractor:
    """Extract compact, reusable facts from a prompt/response turn."""

    _TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b")
    _NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?")

    def extract(self, prompt="", response=""):
        text = f"{prompt or ''} {response or ''}".strip()
        if not text:
            return {"facts": []}

        facts = []

        tickers = self._extract_tickers(text)
        if tickers:
            facts.append(f"Tickers discussed: {', '.join(tickers[:4])}")

        numbers = self._extract_numbers(text)
        if numbers:
            facts.append(f"Values mentioned: {', '.join(numbers[:4])}")

        action = self._extract_action(prompt)
        if action:
            facts.append(f"User intent: {action}")

        return {"facts": facts[:5]}

    def _extract_tickers(self, text):
        ignored = {"AND", "THE", "FOR", "WITH", "PLAN", "RISK"}
        seen = []
        for token in self._TICKER_RE.findall(text or ""):
            if token in ignored:
                continue
            if token not in seen:
                seen.append(token)
        return seen

    def _extract_numbers(self, text):
        seen = []
        for token in self._NUMBER_RE.findall(text or ""):
            if token not in seen:
                seen.append(token)
        return seen

    def _extract_action(self, prompt):
        normalized = str(prompt or "").lower()
        action_markers = [
            "rebalance",
            "summarize",
            "compare",
            "analyze",
            "optimize",
            "reduce risk",
        ]
        for marker in action_markers:
            if marker in normalized:
                return marker
        return ""

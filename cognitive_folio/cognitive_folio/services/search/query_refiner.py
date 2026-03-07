import re


class QueryRefiner:
    """Refine raw search text into concise, provider-friendly queries."""

    _FILLER_PATTERNS = [
        r"\b(can you|could you|please|tell me about|what do you think about|help me with)\b",
        r"\b(i want to know|i need to understand|give me details on)\b",
        r"\b(latest updates on|latest news on)\b",
    ]

    _STOPWORDS = {
        "the", "a", "an", "to", "for", "about", "on", "in", "of", "and", "or", "with", "from", "is", "are"
    }

    def __init__(self, enable_llm=False):
        self.enable_llm = bool(enable_llm)

    def refine(self, query, query_type="general", ticker=None, extraction_fallback=None):
        raw = (query or "").strip()
        if not raw:
            return ""

        if self.enable_llm and callable(extraction_fallback):
            try:
                extracted = (extraction_fallback(raw) or "").strip()
                if extracted:
                    raw = extracted
            except Exception:
                pass

        normalized = raw.lower()
        for pattern in self._FILLER_PATTERNS:
            normalized = re.sub(pattern, " ", normalized, flags=re.IGNORECASE)

        normalized = re.sub(r"[^a-z0-9\s\-\./]", " ", normalized)
        tokens = [token for token in normalized.split() if token and token not in self._STOPWORDS]

        if query_type == "financial":
            prioritized = self._prioritize_financial_tokens(tokens)
        else:
            prioritized = tokens

        if ticker:
            t = str(ticker).strip().upper()
            if t and t.lower() not in prioritized:
                prioritized.append(t.lower())

        compact = " ".join(prioritized[:10]).strip()
        return compact or raw[:120]

    def _prioritize_financial_tokens(self, tokens):
        financial_markers = {
            "earnings", "guidance", "dividend", "revenue", "profit", "margin", "10-k", "10-q", "sec", "filing",
            "valuation", "forecast", "outlook", "analyst", "price", "target", "fed", "inflation", "yield",
        }

        ranked = []
        for token in tokens:
            score = 1
            if token in financial_markers:
                score += 2
            if re.match(r"^[a-z]{1,5}$", token):
                score += 2
            ranked.append((score, token))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [token for _, token in ranked]

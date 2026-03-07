import re


class TrendDetector:
    """Detect trending terms across search results and score per-result trend alignment."""

    _STOPWORDS = {
        "the", "and", "for", "with", "from", "that", "this", "have", "will", "into", "about", "their", "after", "before",
        "update", "news", "latest",
    }

    def score(self, target_result, all_results, query_terms=None, min_frequency=2, weight=0.4):
        query_terms = {str(term).lower() for term in (query_terms or set()) if str(term).strip()}
        trends = self.extract_trends(all_results=all_results, min_frequency=min_frequency, query_terms=query_terms)
        if not trends:
            return 0.0

        target_terms = self._terms(target_result)
        if not target_terms:
            return 0.0

        overlap = target_terms.intersection(trends)
        if not overlap:
            return 0.0

        trend_density = len(overlap) / max(1, len(trends))
        return max(0.0, float(weight or 0.0)) * min(1.0, trend_density * 2.0)

    def extract_trends(self, all_results, min_frequency=2, query_terms=None):
        query_terms = {str(term).lower() for term in (query_terms or set()) if str(term).strip()}
        frequency = {}

        for item in all_results or []:
            for term in self._terms(item):
                frequency[term] = frequency.get(term, 0) + 1

        threshold = max(1, int(min_frequency or 2))
        trending = {term for term, count in frequency.items() if count >= threshold}

        if query_terms:
            aligned = {term for term in trending if term in query_terms}
            if aligned:
                return aligned

        return trending

    def _terms(self, result):
        text = " ".join(
            [
                str((result or {}).get("title") or ""),
                str((result or {}).get("snippet") or ""),
            ]
        ).lower()
        cleaned = re.sub(r"[^a-z0-9 ]", " ", text)
        return {token for token in cleaned.split() if len(token) >= 4 and token not in self._STOPWORDS}

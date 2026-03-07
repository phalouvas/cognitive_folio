from urllib.parse import urlparse
import re


class CrossSourceVerifier:
    """Reward claims corroborated by multiple independent sources."""

    _STOPWORDS = {
        "the", "and", "for", "with", "from", "that", "this", "have", "will", "into", "about", "their", "after", "before"
    }

    _POSITIVE_MARKERS = {
        "beat", "beats", "surge", "surged", "rise", "rises", "up", "gain", "gains", "growth", "strong", "bullish",
        "outperform", "upside", "improve", "improved",
    }

    _NEGATIVE_MARKERS = {
        "miss", "missed", "drop", "dropped", "fall", "falls", "down", "loss", "losses", "weak", "bearish",
        "underperform", "downgrade", "decline", "declined", "risk",
    }

    def score(self, target_result, all_results, min_sources=2, contradiction_penalty=0.25, confidence_boost=0.1):
        target_terms = self._terms(target_result)
        if not target_terms:
            return 0.0

        target_domain = self._domain(target_result)
        target_stance = self._stance(target_result)
        corroborating_domains = set()
        corroborating_count = 0
        contradiction_count = 0

        for candidate in all_results or []:
            if candidate is target_result:
                continue

            domain = self._domain(candidate)
            if not domain or domain == target_domain:
                continue

            overlap = target_terms.intersection(self._terms(candidate))
            if len(overlap) >= 2:
                corroborating_domains.add(domain)
                corroborating_count += 1

                candidate_stance = self._stance(candidate)
                if target_stance != 0 and candidate_stance != 0 and target_stance != candidate_stance:
                    contradiction_count += 1

        # Require at least min_sources distinct corroborators.
        if len(corroborating_domains) < max(1, int(min_sources or 2)):
            return 0.0

        base = min(0.6, 0.18 * len(corroborating_domains) + 0.04 * corroborating_count)
        confidence = float(confidence_boost or 0.0) * min(1.0, len(corroborating_domains) / max(1, int(min_sources or 2)))
        penalty = max(0.0, float(contradiction_penalty or 0.0)) * contradiction_count

        return max(0.0, min(0.8, base + confidence - penalty))

    def _terms(self, result):
        text = " ".join(
            [
                str((result or {}).get("title") or ""),
                str((result or {}).get("snippet") or ""),
            ]
        ).lower()
        cleaned = re.sub(r"[^a-z0-9 ]", " ", text)
        return {token for token in cleaned.split() if len(token) >= 4 and token not in self._STOPWORDS}

    def _domain(self, result):
        try:
            url = str((result or {}).get("url") or "").strip()
            if not url:
                return ""
            return (urlparse(url).hostname or "").lower().strip(".")
        except Exception:
            return ""

    def _stance(self, result):
        terms = self._terms(result)
        if not terms:
            return 0

        positive = sum(1 for token in terms if token in self._POSITIVE_MARKERS)
        negative = sum(1 for token in terms if token in self._NEGATIVE_MARKERS)

        if positive > negative:
            return 1
        if negative > positive:
            return -1
        return 0

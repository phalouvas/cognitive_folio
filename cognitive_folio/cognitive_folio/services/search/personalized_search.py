from urllib.parse import urlparse


class PersonalizedSearch:
    """Score results based on lightweight user/session preference context."""

    def score(self, result, context=None, weight=0.35):
        context = context or {}
        source = str((result or {}).get("source") or "").strip().lower()
        url = str((result or {}).get("url") or "").strip().lower()
        text = " ".join(
            [
                str((result or {}).get("title") or "").lower(),
                str((result or {}).get("snippet") or "").lower(),
                url,
            ]
        )

        preferred_sources = {str(item).strip().lower() for item in (context.get("preferred_sources") or []) if str(item).strip()}
        preferred_domains = {str(item).strip().lower().lstrip(".") for item in (context.get("preferred_domains") or []) if str(item).strip()}
        preferred_tickers = {str(item).strip().lower() for item in (context.get("preferred_tickers") or []) if str(item).strip()}

        score = 0.0
        if preferred_sources and source in preferred_sources:
            score += 0.5

        host = self._host(url)
        if preferred_domains and host:
            for domain in preferred_domains:
                if host == domain or host.endswith(f".{domain}"):
                    score += 0.35
                    break

        if preferred_tickers and any(ticker in text for ticker in preferred_tickers):
            score += 0.35

        preferred_query_type = str(context.get("preferred_query_type") or "").strip().lower()
        if preferred_query_type and preferred_query_type == str(context.get("query_type") or "").strip().lower():
            score += 0.15

        return min(1.0, score) * max(0.0, float(weight or 0.0))

    def _host(self, url):
        if not url:
            return ""
        try:
            return (urlparse(url).hostname or "").lower().strip(".")
        except Exception:
            return ""

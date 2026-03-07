from urllib.parse import urlparse


class DomainAuthorityScorer:
    """Assign authority scores to result URLs based on source domain."""

    DEFAULT_DOMAIN_WEIGHTS = {
        "sec.gov": 1.0,
        "reuters.com": 0.9,
        "bloomberg.com": 0.9,
        "wsj.com": 0.85,
        "ft.com": 0.85,
        "finance.yahoo.com": 0.8,
        "wikipedia.org": 0.75,
    }

    def score(self, url, domain_weights=None, default_weight=0.2):
        if not url:
            return 0.0

        try:
            host = (urlparse(str(url)).hostname or "").lower().strip(".")
        except Exception:
            host = ""

        if not host:
            return 0.0

        weights = self._normalized_weights(domain_weights)
        for domain, weight in weights.items():
            if host == domain or host.endswith(f".{domain}"):
                return float(weight)

        return float(default_weight)

    def _normalized_weights(self, domain_weights):
        raw = domain_weights if isinstance(domain_weights, dict) else self.DEFAULT_DOMAIN_WEIGHTS
        normalized = {}
        for domain, weight in (raw or {}).items():
            key = str(domain or "").strip().lower().lstrip(".")
            if not key:
                continue
            try:
                normalized[key] = float(weight)
            except Exception:
                continue
        return normalized or dict(self.DEFAULT_DOMAIN_WEIGHTS)

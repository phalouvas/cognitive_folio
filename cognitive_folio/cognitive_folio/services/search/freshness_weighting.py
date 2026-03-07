from datetime import datetime, timezone
import math


class FreshnessWeighting:
    """Compute recency score for search results."""

    _DATE_KEYS = ("published_at", "published", "date", "file_date")

    def score(self, result, query_type="general", half_life_days=21, now_utc=None):
        published_at = self._extract_date(result)
        if not published_at:
            return 0.0

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        age_days = max(0.0, (now_utc - published_at).total_seconds() / 86400.0)
        decay = math.exp(-age_days / max(1.0, float(half_life_days or 21)))

        # Financial queries prioritize recency more aggressively.
        multiplier = 0.6 if str(query_type or "").lower() == "financial" else 0.35
        return max(0.0, min(1.0, decay)) * multiplier

    def _extract_date(self, result):
        result = result or {}
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}

        candidates = []
        for key in self._DATE_KEYS:
            value = result.get(key)
            if value:
                candidates.append(value)
            meta_value = metadata.get(key)
            if meta_value:
                candidates.append(meta_value)

        for candidate in candidates:
            parsed = self._parse_date(candidate)
            if parsed:
                return parsed

        return None

    def _parse_date(self, value):
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

        text = str(value or "").strip()
        if not text:
            return None

        normalized = text.replace("Z", "+00:00")
        patterns = (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
        )

        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            pass

        for pattern in patterns:
            try:
                parsed = datetime.strptime(normalized, pattern)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except Exception:
                continue

        return None

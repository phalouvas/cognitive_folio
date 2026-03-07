import json
import re

import frappe


class SearchSessionTracker:
    """Track recent search history to support follow-up query continuity."""

    _CACHE_KEY_PREFIX = "cf:search_session:"
    _FOLLOWUP_MARKERS = {
        "it", "that", "those", "them", "same", "more", "latest", "update", "updates", "again", "also",
        "there", "here", "this", "these",
    }

    def record_search(self, session_key, query, query_type="general", providers=None, results=None, max_entries=25):
        key = self._cache_key(session_key)
        history = self._load_history(key)

        top_urls = []
        for item in (results or [])[:3]:
            url = str((item or {}).get("url") or "").strip()
            if url:
                top_urls.append(url)

        history.append(
            {
                "query": self._compact(query, 240),
                "query_type": str(query_type or "general").strip().lower() or "general",
                "providers": [str(value).strip().lower() for value in (providers or []) if str(value or "").strip()],
                "top_urls": top_urls,
            }
        )
        history = history[-max(1, int(max_entries or 25)) :]

        self._save_history(key, history)
        return {"stored": True, "items": len(history)}

    def expand_follow_up_query(self, query, session_key, max_items=3, max_chars=180):
        normalized_query = " ".join(str(query or "").split())
        if not self._looks_like_follow_up(normalized_query):
            return normalized_query

        context = self._recent_topic(session_key, max_items=max_items, max_chars=max_chars)
        if not context:
            return normalized_query

        lowered = normalized_query.lower()
        if context.lower() in lowered:
            return normalized_query

        return f"{normalized_query} about {context}".strip()

    def get_recent_history(self, session_key, max_items=5):
        key = self._cache_key(session_key)
        history = self._load_history(key)
        return list(history)[-max(1, int(max_items or 5)) :]

    def _recent_topic(self, session_key, max_items=3, max_chars=180):
        key = self._cache_key(session_key)
        history = self._load_history(key)
        if not history:
            return ""

        recent = list(history)[-max(1, int(max_items or 3)) :]
        topics = []
        for item in reversed(recent):
            query = str((item or {}).get("query") or "").strip()
            if not query:
                continue
            if self._looks_like_follow_up(query):
                continue
            topic = " ".join(query.split()[:6]).strip()
            if topic and topic not in topics:
                topics.append(topic)

        context = ", ".join(topics[:2]).strip()
        if len(context) > int(max_chars or 180):
            context = context[: int(max_chars or 180) - 3] + "..."
        return context

    def _cache_key(self, session_key):
        return f"{self._CACHE_KEY_PREFIX}{session_key or 'default'}"

    def _load_history(self, cache_key):
        try:
            raw = frappe.cache().get_value(cache_key)
            if not raw:
                return []
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    def _save_history(self, cache_key, history):
        try:
            frappe.cache().set_value(cache_key, json.dumps(history, ensure_ascii=False, default=str))
        except Exception:
            frappe.log_error(title="SearchSessionTracker cache write error", message=frappe.get_traceback())

    def _looks_like_follow_up(self, query):
        lowered = str(query or "").strip().lower()
        if not lowered:
            return False

        tokens = [token for token in re.split(r"\s+", lowered) if token]
        if len(tokens) <= 3:
            return True

        return any(token in self._FOLLOWUP_MARKERS for token in tokens)

    def _compact(self, text, max_len):
        value = " ".join(str(text or "").split())
        if len(value) <= max_len:
            return value
        return value[: max_len - 3] + "..."

# pyright: reportMissingImports=false
import hashlib
import json
import time

try:
    import frappe
except Exception:  # pragma: no cover - fallback for non-Frappe test runs
    frappe = None


class _CacheStore:
    """Small cache abstraction with Frappe-cache first and in-memory fallback."""

    _LOCAL_STORE = {}

    def __init__(self, namespace):
        self.namespace = str(namespace or "cognitive_folio")

    def _key(self, key):
        return f"{self.namespace}:{key}"

    def _now(self):
        return time.time()

    def get(self, key):
        namespaced = self._key(key)

        if frappe:
            try:
                payload = frappe.cache().get_value(namespaced)
                if isinstance(payload, dict) and payload.get("expires_at", 0) > self._now():
                    return payload.get("value")
                if payload:
                    frappe.cache().delete_value(namespaced)
            except Exception:
                pass

        payload = self._LOCAL_STORE.get(namespaced)
        if not payload:
            return None
        if payload.get("expires_at", 0) <= self._now():
            self._LOCAL_STORE.pop(namespaced, None)
            return None
        return payload.get("value")

    def set(self, key, value, ttl_seconds):
        ttl = max(1, int(ttl_seconds or 1))
        payload = {
            "value": value,
            "expires_at": self._now() + ttl,
        }
        namespaced = self._key(key)

        if frappe:
            try:
                frappe.cache().set_value(namespaced, payload, expires_in_sec=ttl)
            except Exception:
                pass

        self._LOCAL_STORE[namespaced] = payload


class SearchResultCache:
    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = bool(self.config.get("search_cache_enabled", True))
        namespace = str(self.config.get("search_cache_namespace") or "cf:search").strip()
        self._store = _CacheStore(namespace)

    def _ttl_seconds(self, query_type, date_range=None):
        if str(date_range or "").strip().lower() in {"day", "week"}:
            return int(self.config.get("search_cache_ttl_realtime_seconds", 120) or 120)
        if str(query_type or "general").lower() == "financial":
            return int(self.config.get("search_cache_ttl_financial_seconds", 300) or 300)
        return int(self.config.get("search_cache_ttl_general_seconds", 900) or 900)

    def _hash(self, payload):
        text = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def make_key(self, operation, payload):
        return f"{operation}:{self._hash(payload)}"

    def get(self, operation, payload):
        if not self.enabled:
            return None
        return self._store.get(self.make_key(operation, payload))

    def set(self, operation, payload, value, query_type="general", date_range=None):
        if not self.enabled:
            return
        self._store.set(
            self.make_key(operation, payload),
            value,
            ttl_seconds=self._ttl_seconds(query_type=query_type, date_range=date_range),
        )


class ContentSummarizationCache:
    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = bool(self.config.get("content_summary_cache_enabled", True))
        self._ttl = int(self.config.get("content_summary_cache_ttl_seconds", 3600) or 3600)
        namespace = str(self.config.get("content_summary_cache_namespace") or "cf:content").strip()
        self._store = _CacheStore(namespace)

    def _key(self, url, max_chars):
        payload = {
            "url": str(url or "").strip().lower(),
            "max_chars": int(max_chars or 0),
        }
        text = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, url, max_chars):
        if not self.enabled:
            return None
        return self._store.get(self._key(url=url, max_chars=max_chars))

    def set(self, url, max_chars, content):
        if not self.enabled:
            return
        self._store.set(self._key(url=url, max_chars=max_chars), content, ttl_seconds=self._ttl)


class ToolResultCache:
    READ_ONLY_TOOLS = {
        "get_security_snapshot",
        "get_portfolio_holdings",
        "get_latest_security_news",
        "web_search",
        "search_financial",
        "fetch_url_content",
        "normalize_ticker",
    }

    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = bool(self.config.get("tool_result_cache_enabled", True))
        self._ttl = int(self.config.get("tool_result_cache_ttl_seconds", 600) or 600)
        namespace = str(self.config.get("tool_result_cache_namespace") or "cf:tool").strip()
        self._store = _CacheStore(namespace)

    def _key(self, function_name, args_key, chat_name, portfolio_name, security_name, dynamic_registration_enabled):
        payload = {
            "function_name": str(function_name or "").strip().lower(),
            "args_key": str(args_key or "{}"),
            "chat": chat_name,
            "portfolio": portfolio_name,
            "security": security_name,
            "dynamic_registration_enabled": bool(dynamic_registration_enabled),
        }
        text = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def should_cache(self, function_name):
        return str(function_name or "").strip().lower() in self.READ_ONLY_TOOLS

    def get(self, function_name, args_key, chat_name, portfolio_name, security_name, dynamic_registration_enabled):
        if not self.enabled or not self.should_cache(function_name):
            return None
        key = self._key(function_name, args_key, chat_name, portfolio_name, security_name, dynamic_registration_enabled)
        return self._store.get(key)

    def set(self, function_name, args_key, chat_name, portfolio_name, security_name, dynamic_registration_enabled, result):
        if not self.enabled or not self.should_cache(function_name):
            return
        key = self._key(function_name, args_key, chat_name, portfolio_name, security_name, dynamic_registration_enabled)
        self._store.set(key, result, ttl_seconds=self._ttl)


class PredictivePrefetching:
    """Lightweight query prediction and prefetch strategy."""

    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = bool(self.config.get("search_prefetch_enabled", False))
        self.max_queries = max(0, int(self.config.get("search_prefetch_max_queries", 2) or 2))

    def predict_queries(self, query, query_type, ticker=None):
        if not self.enabled or self.max_queries <= 0:
            return []

        base = str(query or "").strip()
        if not base:
            return []

        candidates = []
        if str(query_type or "general").lower() == "financial":
            if ticker:
                symbol = str(ticker).upper().strip()
                candidates.extend([
                    f"{symbol} latest filing",
                    f"{symbol} earnings call highlights",
                ])
            candidates.append(f"{base} latest updates")
        else:
            candidates.extend([
                f"{base} latest news",
                f"{base} analysis",
            ])

        deduped = []
        seen = set([base.lower()])
        for item in candidates:
            lowered = item.lower().strip()
            if lowered and lowered not in seen:
                seen.add(lowered)
                deduped.append(item)
            if len(deduped) >= self.max_queries:
                break
        return deduped

    def prefetch(self, callback, queries, max_results=2):
        if not self.enabled:
            return {"enabled": False, "prefetched": 0}

        prefetched = 0
        for query in queries[: self.max_queries]:
            try:
                callback(query=query, num_results=max_results, is_prefetch=True)
                prefetched += 1
            except Exception:
                continue
        return {"enabled": True, "prefetched": prefetched}

import json


class ToolSelfCorrector:
    """Apply lightweight deterministic fixes to failed tool-call arguments."""

    def build_retry_arguments(self, function_name, arguments_raw, tool_result, context=None):
        context = context or {}
        result = tool_result or {}
        if not isinstance(result, dict):
            return None
        if result.get("ok"):
            return None

        args = self._safe_json_loads(arguments_raw)
        if not isinstance(args, dict):
            args = {}
        corrected = dict(args)

        if function_name in ("web_search", "search_financial") and not corrected.get("query"):
            fallback_query = (context.get("latest_user_message") or "").strip()
            if fallback_query:
                corrected["query"] = fallback_query[:200]

        if function_name == "fetch_url_content":
            url = str(corrected.get("url") or "").strip()
            if url and not url.startswith(("http://", "https://")) and "." in url:
                corrected["url"] = f"https://{url}"

        for key in ("max_results", "limit", "news_limit", "max_chars"):
            if key not in corrected:
                continue
            try:
                value = int(corrected.get(key))
            except Exception:
                continue
            corrected[key] = max(1, value)

        return corrected if corrected != args else None

    def _safe_json_loads(self, value):
        if isinstance(value, dict):
            return value
        if value in (None, ""):
            return {}
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
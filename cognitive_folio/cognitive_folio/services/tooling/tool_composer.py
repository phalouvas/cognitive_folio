import json
import re


class ToolComposer:
    """Resolve lightweight placeholders in tool arguments using prior tool outputs."""

    _PLACEHOLDER = re.compile(r"^\$\{(last|tool:[A-Za-z0-9_\-]+):([A-Za-z0-9_\-.]+)\}$")

    def compose_arguments_raw(self, arguments_raw, context):
        args = self._safe_json_loads(arguments_raw)
        composed = self._replace_placeholders(args, context or {})
        return json.dumps(composed, ensure_ascii=False, default=str)

    def _replace_placeholders(self, node, context):
        if isinstance(node, dict):
            return {key: self._replace_placeholders(value, context) for key, value in node.items()}
        if isinstance(node, list):
            return [self._replace_placeholders(value, context) for value in node]
        if not isinstance(node, str):
            return node

        match = self._PLACEHOLDER.match(node.strip())
        if not match:
            return node

        source, path = match.groups()
        if source == "last":
            base = context.get("last")
        else:
            tool_name = source.split(":", 1)[1]
            tool_entries = (context.get("tools") or {}).get(tool_name) or []
            base = tool_entries[-1] if tool_entries else None

        resolved = self._resolve_path(base, path)
        return resolved if resolved is not None else node

    def _resolve_path(self, base, path):
        current = base
        for part in (path or "").split("."):
            if current is None:
                return None
            if isinstance(current, list):
                if not part.isdigit():
                    return None
                index = int(part)
                if index < 0 or index >= len(current):
                    return None
                current = current[index]
                continue
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

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
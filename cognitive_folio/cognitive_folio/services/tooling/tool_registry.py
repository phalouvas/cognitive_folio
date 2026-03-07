import frappe


class ToolRegistry:
    """Merge built-in and hook-registered tool definitions and handlers."""

    def __init__(self, chat_message):
        self.chat_message = chat_message

    def merge_tool_definitions(self, base_tools):
        merged = list(base_tools or [])
        dynamic = self._load_dynamic_tool_definitions()
        existing = {
            ((tool or {}).get("function") or {}).get("name")
            for tool in merged
            if isinstance(tool, dict)
        }
        for tool in dynamic:
            name = ((tool or {}).get("function") or {}).get("name")
            if not name or name in existing:
                continue
            merged.append(tool)
            existing.add(name)
        return merged

    def get_dynamic_handlers(self):
        handlers = {}
        hooks = frappe.get_hooks("cognitive_folio_tool_handlers", default={}) or {}

        if isinstance(hooks, dict):
            for tool_name, values in hooks.items():
                handler_path = self._first_value(values)
                handler = self._resolve_callable(handler_path)
                if handler:
                    handlers[str(tool_name)] = handler
            return handlers

        if isinstance(hooks, list):
            for item in hooks:
                if not isinstance(item, dict):
                    continue
                for tool_name, handler_path in item.items():
                    handler = self._resolve_callable(handler_path)
                    if handler:
                        handlers[str(tool_name)] = handler
        return handlers

    def _load_dynamic_tool_definitions(self):
        output = []
        hooks = frappe.get_hooks("cognitive_folio_tool_definitions", default=[]) or []
        entries = hooks if isinstance(hooks, list) else [hooks]
        for entry in entries:
            if isinstance(entry, dict):
                if ((entry.get("function") or {}).get("name")):
                    output.append(entry)
                continue

            candidate = self._resolve_callable(entry)
            if not candidate:
                continue
            try:
                value = candidate(self.chat_message)
            except TypeError:
                value = candidate()
            except Exception:
                frappe.log_error(title="Dynamic tool definition error", message=frappe.get_traceback())
                continue

            if isinstance(value, dict) and ((value.get("function") or {}).get("name")):
                output.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and ((item.get("function") or {}).get("name")):
                        output.append(item)
        return output

    def _resolve_callable(self, candidate):
        if callable(candidate):
            return candidate
        if not candidate:
            return None
        try:
            resolved = frappe.get_attr(candidate)
            return resolved if callable(resolved) else None
        except Exception:
            return None

    def _first_value(self, value):
        if isinstance(value, (list, tuple)):
            return value[0] if value else None
        return value
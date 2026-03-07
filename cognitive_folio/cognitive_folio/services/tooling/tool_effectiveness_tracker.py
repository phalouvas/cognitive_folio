class ToolEffectivenessTracker:
    """Track per-tool execution outcomes for runtime learning telemetry."""

    def __init__(self):
        self._stats = {}

    def record(self, tool_name, ok, duration_ms, retried=False):
        name = (tool_name or "unknown").strip() or "unknown"
        entry = self._stats.setdefault(
            name,
            {
                "calls": 0,
                "success": 0,
                "failure": 0,
                "retries": 0,
                "total_duration_ms": 0.0,
            },
        )
        entry["calls"] += 1
        entry["success" if ok else "failure"] += 1
        if retried:
            entry["retries"] += 1
        try:
            entry["total_duration_ms"] += float(duration_ms or 0.0)
        except Exception:
            pass

    def as_dict(self):
        summary = {}
        for tool_name, entry in self._stats.items():
            calls = max(1, int(entry["calls"]))
            summary[tool_name] = {
                "calls": int(entry["calls"]),
                "success": int(entry["success"]),
                "failure": int(entry["failure"]),
                "retries": int(entry["retries"]),
                "avg_duration_ms": round(float(entry["total_duration_ms"]) / calls, 2),
                "success_rate": round(float(entry["success"]) / calls, 4),
            }
        return summary
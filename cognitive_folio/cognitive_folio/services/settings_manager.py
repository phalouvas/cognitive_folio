import os


class SettingsManager:
    """Typed and validated access to CF Settings values."""

    def __init__(self, settings):
        self.settings = settings

    def environment(self):
        env = os.getenv("COGNITIVE_FOLIO_ENV")
        if env:
            return env.strip().lower()

        configured = None
        try:
            configured = self.settings.get("deployment_environment")
        except Exception:
            configured = None

        return (configured or "production").strip().lower()

    def get_feature_flag(self, fieldname, default=False):
        return self.get_bool(fieldname, default=default)

    def get_bool(self, fieldname, default=False):
        raw = self.settings.get(fieldname)
        if raw is None:
            return bool(default)

        if isinstance(raw, bool):
            return raw

        if isinstance(raw, (int, float)):
            return bool(raw)

        normalized = str(raw).strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False

        return bool(default)

    def get_int(self, fieldname, default, minimum=None, maximum=None):
        try:
            value = int(self.settings.get(fieldname))
        except (TypeError, ValueError):
            value = int(default)

        if minimum is not None and value < minimum:
            value = minimum
        if maximum is not None and value > maximum:
            value = maximum
        return value

    def get_float(self, fieldname, default, minimum=None, maximum=None):
        try:
            value = float(self.settings.get(fieldname))
        except (TypeError, ValueError):
            value = float(default)

        if minimum is not None and value < minimum:
            value = minimum
        if maximum is not None and value > maximum:
            value = maximum
        return value

    def validate_chat_schema(self):
        """Return validation details for important chat settings fields."""
        errors = []

        checks = [
            ("chat_default_max_tokens", 1, 65536),
            ("chat_max_tokens_cap", 1, 65536),
            ("reasoner_default_max_tokens", 1, 65536),
            ("reasoner_max_tokens_cap", 1, 65536),
            ("max_context_tokens", 2048, 512000),
            ("max_api_retries", 1, 20),
            ("stream_flush_min_char_delta", 1, 5000),
            ("max_tool_rounds", 1, 20),
            ("max_tool_calls_per_round", 1, 20),
            ("tool_result_max_chars", 200, 50000),
            ("web_search_max_results", 1, 20),
        ]

        for fieldname, min_value, max_value in checks:
            raw = self.settings.get(fieldname)
            if raw in (None, ""):
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError):
                errors.append(f"{fieldname} must be an integer")
                continue

            if value < min_value or value > max_value:
                errors.append(f"{fieldname} must be between {min_value} and {max_value}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "environment": self.environment(),
        }

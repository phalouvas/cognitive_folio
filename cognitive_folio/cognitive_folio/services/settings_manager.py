import os
import json


class SettingsManager:
    """Typed and validated access to CF Settings values."""

    def __init__(self, settings):
        self.settings = settings
        self._feature_flags_cache = None

    def _get_setting_value(self, fieldname, default=None):
        try:
            value = self.settings.get(fieldname)
        except Exception:
            value = None
        return default if value is None else value

    def _coerce_bool(self, raw, default=False):
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

    def _coerce_json_object(self, raw, default=None):
        if default is None:
            default = {}

        if raw in (None, ""):
            return dict(default)

        if isinstance(raw, dict):
            return raw

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        return dict(default)

    def _parse_json_object_strict(self, raw):
        if raw in (None, ""):
            return {}, None
        if isinstance(raw, dict):
            return raw, None

        try:
            parsed = json.loads(raw)
        except Exception:
            return None, "must be valid JSON"

        if not isinstance(parsed, dict):
            return None, "must be a JSON object"

        return parsed, None

    def _environment_variable_candidates(self, fieldname):
        normalized_field = str(fieldname or "").strip().upper().replace("-", "_")
        current_env = self.environment().upper()
        return [
            f"COGNITIVE_FOLIO_{current_env}_{normalized_field}",
            f"COGNITIVE_FOLIO_{normalized_field}",
        ]

    def _get_environment_override(self, fieldname):
        for key in self._environment_variable_candidates(fieldname):
            value = os.getenv(key)
            if value not in (None, ""):
                return value
        return None

    def environment(self):
        env = os.getenv("COGNITIVE_FOLIO_ENV")
        if env:
            return env.strip().lower()

        configured = self._get_setting_value("deployment_environment")

        return (configured or "production").strip().lower()

    def feature_flags(self):
        if self._feature_flags_cache is not None:
            return self._feature_flags_cache

        settings_flags = self._coerce_json_object(self._get_setting_value("feature_flags_json"), default={})
        env_flags = self._coerce_json_object(os.getenv("COGNITIVE_FOLIO_FEATURE_FLAGS"), default={})

        merged = dict(settings_flags)
        merged.update(env_flags)
        self._feature_flags_cache = merged
        return merged

    def get_feature_flag(self, fieldname, default=False):
        flags = self.feature_flags()
        if fieldname in flags:
            return self._coerce_bool(flags.get(fieldname), default=default)

        return self.get_bool(fieldname, default=default)

    def get_bool(self, fieldname, default=False):
        override = self._get_environment_override(fieldname)
        if override not in (None, ""):
            return self._coerce_bool(override, default=default)

        raw = self._get_setting_value(fieldname)
        return self._coerce_bool(raw, default=default)

    def get_int(self, fieldname, default, minimum=None, maximum=None):
        override = self._get_environment_override(fieldname)
        try:
            value = int(override if override not in (None, "") else self._get_setting_value(fieldname))
        except (TypeError, ValueError):
            value = int(default)

        if minimum is not None and value < minimum:
            value = minimum
        if maximum is not None and value > maximum:
            value = maximum
        return value

    def get_float(self, fieldname, default, minimum=None, maximum=None):
        override = self._get_environment_override(fieldname)
        try:
            value = float(override if override not in (None, "") else self._get_setting_value(fieldname))
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
            raw = self._get_setting_value(fieldname)
            if raw in (None, ""):
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError):
                errors.append(f"{fieldname} must be an integer")
                continue

            if value < min_value or value > max_value:
                errors.append(f"{fieldname} must be between {min_value} and {max_value}")

        feature_flags_raw = self._get_setting_value("feature_flags_json")
        _, parse_error = self._parse_json_object_strict(feature_flags_raw)
        if parse_error:
            errors.append(f"feature_flags_json {parse_error}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "environment": self.environment(),
        }

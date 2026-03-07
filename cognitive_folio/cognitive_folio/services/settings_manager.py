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

    def get_feature_value(self, fieldname, default=None):
        flags = self.feature_flags()
        if fieldname in flags:
            return flags.get(fieldname)
        return default

    def get_int_config(self, fieldname, default, minimum=None, maximum=None):
        override = self._get_environment_override(fieldname)
        value = override if override not in (None, "") else self.get_feature_value(fieldname, None)
        if value is None:
            return self.get_int(fieldname, default, minimum=minimum, maximum=maximum)

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default)

        if minimum is not None and parsed < minimum:
            parsed = minimum
        if maximum is not None and parsed > maximum:
            parsed = maximum
        return parsed

    def get_float_config(self, fieldname, default, minimum=None, maximum=None):
        override = self._get_environment_override(fieldname)
        value = override if override not in (None, "") else self.get_feature_value(fieldname, None)
        if value is None:
            return self.get_float(fieldname, default, minimum=minimum, maximum=maximum)

        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = float(default)

        if minimum is not None and parsed < minimum:
            parsed = minimum
        if maximum is not None and parsed > maximum:
            parsed = maximum
        return parsed

    def get_list_config(self, fieldname, default=None):
        if default is None:
            default = []

        override = self._get_environment_override(fieldname)
        raw = override if override not in (None, "") else self.get_feature_value(fieldname, None)
        if raw is None:
            return list(default)

        if isinstance(raw, (list, tuple, set)):
            return [str(item).strip() for item in raw if str(item).strip()]

        if isinstance(raw, str):
            text = raw.strip()
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [part.strip() for part in text.split(",") if part.strip()]

        return list(default)

    def get_planner_config(self):
        return {
            "enabled": self.get_feature_flag("planner_enabled", default=True),
            "inject_system_plan": self.get_feature_flag("planner_inject_system_prompt", default=True),
            "enforce_recommended_tools": self.get_feature_flag("planner_enforce_recommended_tools", default=False),
            "max_plan_steps": self.get_int_config("planner_max_plan_steps", default=6, minimum=3, maximum=10),
            "max_recommended_tools": self.get_int_config("planner_max_recommended_tools", default=4, minimum=1, maximum=10),
            "financial_markers": self.get_list_config("planner_financial_markers", default=[]),
            "research_markers": self.get_list_config("planner_research_markers", default=[]),
            "long_query_chars": self.get_int_config("planner_long_query_chars", default=450, minimum=150, maximum=4000),
            "complexity_high_threshold": self.get_int_config("planner_complexity_high_threshold", default=3, minimum=2, maximum=8),
            "complexity_medium_threshold": self.get_int_config("planner_complexity_medium_threshold", default=1, minimum=1, maximum=6),
        }

    def get_tool_execution_config(self):
        return {
            "composition_enabled": self.get_feature_flag("tool_composition_enabled", default=True),
            "self_correction_enabled": self.get_feature_flag("tool_self_correction_enabled", default=True),
            "dynamic_registration_enabled": self.get_feature_flag("tool_dynamic_registration_enabled", default=True),
            "max_corrections_per_call": self.get_int_config("tool_max_corrections_per_call", default=1, minimum=0, maximum=3),
        }

    def get_memory_config(self):
        return {
            "enabled": self.get_feature_flag("conversation_memory_enabled", default=True),
            "max_items": self.get_int_config("conversation_memory_max_items", default=6, minimum=1, maximum=20),
            "max_relevant_items": self.get_int_config("conversation_memory_max_relevant_items", default=3, minimum=1, maximum=10),
            "max_chars": self.get_int_config("conversation_memory_max_chars", default=1200, minimum=200, maximum=6000),
            "cache_items": self.get_int_config("conversation_memory_cache_items", default=30, minimum=5, maximum=100),
            "vector_enabled": self.get_feature_flag("vector_memory_enabled", default=True),
            "vector_max_items": self.get_int_config("vector_memory_max_items", default=3, minimum=1, maximum=10),
            "vector_max_chars": self.get_int_config("vector_memory_max_chars", default=700, minimum=200, maximum=4000),
            "vector_cache_items": self.get_int_config("vector_memory_cache_items", default=60, minimum=10, maximum=200),
            "vector_persist_enabled": self.get_feature_flag("vector_memory_persist_enabled", default=False),
            "vector_store_max_records_per_chat": self.get_int_config("vector_memory_store_max_records_per_chat", default=300, minimum=20, maximum=5000),
            "vector_store_max_age_days": self.get_int_config("vector_memory_store_max_age_days", default=180, minimum=7, maximum=3650),
            "vector_embedding_dims": self.get_int_config("vector_memory_embedding_dims", default=96, minimum=16, maximum=512),
            "vector_similarity_mode": str(self.get_feature_value("vector_memory_similarity_mode", "embedding") or "embedding").strip().lower(),
        }

    def get_search_provider_config(self):
        general_chain_raw = (
            self._get_environment_override("search_general_provider_chain")
            or self.get_feature_value("search_general_provider_chain", None)
            or self._get_setting_value("web_search_providers")
        )
        financial_chain_raw = (
            self._get_environment_override("search_financial_provider_chain")
            or self.get_feature_value("search_financial_provider_chain", None)
        )
        domains_raw = (
            self._get_environment_override("web_search_financial_domains")
            or self.get_feature_value("search_financial_domains", None)
            or self._get_setting_value("web_search_financial_domains")
        )
        preferred_sources_raw = (
            self._get_environment_override("search_preferred_sources")
            or self.get_feature_value("search_preferred_sources", None)
            or []
        )
        preferred_domains_raw = (
            self._get_environment_override("search_preferred_domains")
            or self.get_feature_value("search_preferred_domains", None)
            or []
        )

        serpapi_key = (
            self._get_environment_override("search_serpapi_api_key")
            or self.get_feature_value("search_serpapi_api_key", None)
            or ""
        )
        domain_weights_raw = (
            self._get_environment_override("search_domain_authority_weights")
            or self.get_feature_value("search_domain_authority_weights", None)
            or {}
        )
        sec_user_agent = (
            self._get_environment_override("search_sec_user_agent")
            or self.get_feature_value("search_sec_user_agent", None)
            or "CognitiveFolio/1.0 research@example.com"
        )

        return {
            "general_chain": self._parse_list_value(general_chain_raw, default=["ddgs", "wikipedia"]),
            "financial_chain": self._parse_list_value(
                financial_chain_raw,
                default=["ddgs", "sec_edgar", "financial_news", "yahoo_finance"],
            ),
            "max_results": self.get_int("web_search_max_results", default=5, minimum=1, maximum=10),
            "financial_domains": self._parse_list_value(
                domains_raw,
                default=["reuters.com", "bloomberg.com", "wsj.com", "ft.com", "marketwatch.com"],
            ),
            "serpapi_enabled": self.get_feature_flag("search_serpapi_enabled", default=False),
            "serpapi_api_key": str(serpapi_key or "").strip(),
            "serpapi_engine": str(
                self._get_environment_override("search_serpapi_engine")
                or self.get_feature_value("search_serpapi_engine", "google")
                or "google"
            ).strip().lower(),
            "sec_realtime_enabled": self.get_feature_flag("search_sec_realtime_enabled", default=True),
            "sec_user_agent": str(sec_user_agent).strip() or "CognitiveFolio/1.0 research@example.com",
            "provider_timeout_seconds": self.get_int_config("search_provider_timeout_seconds", default=15, minimum=3, maximum=60),
            "query_refiner_enabled": self.get_feature_flag("search_query_refiner_enabled", default=True),
            "query_refiner_llm_enabled": self.get_feature_flag("search_query_refiner_llm_enabled", default=False),
            "result_reranker_enabled": self.get_feature_flag("search_result_reranker_enabled", default=True),
            "result_reranker_top_k": self.get_int_config("search_result_reranker_top_k", default=8, minimum=1, maximum=20),
            "freshness_weighting_enabled": self.get_feature_flag("search_freshness_weighting_enabled", default=True),
            "freshness_half_life_days": self.get_int_config("search_freshness_half_life_days", default=21, minimum=1, maximum=365),
            "cross_source_verifier_enabled": self.get_feature_flag("search_cross_source_verifier_enabled", default=True),
            "cross_source_min_sources": self.get_int_config("search_cross_source_min_sources", default=2, minimum=1, maximum=5),
            "cross_source_contradiction_penalty": self.get_float_config(
                "search_cross_source_contradiction_penalty",
                default=0.25,
                minimum=0.0,
                maximum=2.0,
            ),
            "cross_source_confidence_boost": self.get_float_config(
                "search_cross_source_confidence_boost",
                default=0.1,
                minimum=0.0,
                maximum=1.0,
            ),
            "domain_authority_enabled": self.get_feature_flag("search_domain_authority_enabled", default=True),
            "domain_authority_default_weight": self.get_float_config(
                "search_domain_authority_default_weight",
                default=0.2,
                minimum=0.0,
                maximum=2.0,
            ),
            "domain_authority_weights": self._coerce_json_object(domain_weights_raw, default={}),
            "session_tracker_enabled": self.get_feature_flag("search_session_tracker_enabled", default=True),
            "session_max_entries": self.get_int_config("search_session_max_entries", default=25, minimum=5, maximum=200),
            "session_context_max_items": self.get_int_config("search_session_context_max_items", default=3, minimum=1, maximum=10),
            "session_context_max_chars": self.get_int_config("search_session_context_max_chars", default=180, minimum=60, maximum=1000),
            "session_followup_expand_enabled": self.get_feature_flag("search_session_followup_expand_enabled", default=True),
            "semantic_search_enabled": self.get_feature_flag("search_semantic_search_enabled", default=False),
            "semantic_embedding_dims": self.get_int_config("search_semantic_embedding_dims", default=96, minimum=16, maximum=512),
            "semantic_score_weight": self.get_float_config("search_semantic_score_weight", default=0.6, minimum=0.0, maximum=2.0),
            "trend_detector_enabled": self.get_feature_flag("search_trend_detector_enabled", default=False),
            "trend_min_frequency": self.get_int_config("search_trend_min_frequency", default=2, minimum=1, maximum=10),
            "trend_score_weight": self.get_float_config("search_trend_score_weight", default=0.4, minimum=0.0, maximum=2.0),
            "personalized_search_enabled": self.get_feature_flag("search_personalized_search_enabled", default=False),
            "personalized_score_weight": self.get_float_config("search_personalized_score_weight", default=0.35, minimum=0.0, maximum=2.0),
            "personalized_history_items": self.get_int_config("search_personalized_history_items", default=5, minimum=1, maximum=20),
            "preferred_sources": self._parse_list_value(preferred_sources_raw, default=[]),
            "preferred_domains": self._parse_list_value(preferred_domains_raw, default=[]),
        }

    def _parse_list_value(self, raw, default=None):
        if default is None:
            default = []

        if raw is None:
            return list(default)

        if isinstance(raw, (list, tuple, set)):
            return [str(item).strip() for item in raw if str(item).strip()]

        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return list(default)
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [part.strip() for part in text.split(",") if part.strip()]

        return list(default)

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

        planner_config = self.get_planner_config()
        if planner_config["complexity_medium_threshold"] >= planner_config["complexity_high_threshold"]:
            errors.append("planner_complexity_medium_threshold must be less than planner_complexity_high_threshold")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "environment": self.environment(),
        }

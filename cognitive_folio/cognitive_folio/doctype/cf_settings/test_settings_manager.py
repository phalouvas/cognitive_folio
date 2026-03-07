from unittest.mock import MagicMock, patch
import unittest

from cognitive_folio.cognitive_folio.services.settings_manager import SettingsManager


class TestSettingsManager(unittest.TestCase):
    def _make_settings(self, values=None):
        values = values or {}
        settings = MagicMock()
        settings.get.side_effect = lambda key: values.get(key)
        return settings

    def test_environment_defaults_to_production(self):
        settings = self._make_settings({})
        manager = SettingsManager(settings)
        with patch.dict("os.environ", {}, clear=False):
            self.assertEqual(manager.environment(), "production")

    def test_environment_uses_env_var(self):
        settings = self._make_settings({"deployment_environment": "staging"})
        manager = SettingsManager(settings)
        with patch.dict("os.environ", {"COGNITIVE_FOLIO_ENV": "dev"}, clear=False):
            self.assertEqual(manager.environment(), "dev")

    def test_get_int_prefers_environment_override(self):
        settings = self._make_settings({"max_tool_rounds": 8, "deployment_environment": "staging"})
        manager = SettingsManager(settings)
        with patch.dict("os.environ", {"COGNITIVE_FOLIO_STAGING_MAX_TOOL_ROUNDS": "12"}, clear=False):
            self.assertEqual(manager.get_int("max_tool_rounds", 8, minimum=1, maximum=20), 12)

    def test_get_feature_flag_prefers_json_flags(self):
        settings = self._make_settings({"feature_flags_json": '{"planner_v2": true}', "planner_v2": 0})
        manager = SettingsManager(settings)
        self.assertTrue(manager.get_feature_flag("planner_v2", default=False))

    def test_get_feature_flag_prefers_env_flags(self):
        settings = self._make_settings({"feature_flags_json": '{"planner_v2": false}'})
        manager = SettingsManager(settings)
        with patch.dict("os.environ", {"COGNITIVE_FOLIO_FEATURE_FLAGS": '{"planner_v2": true}'}, clear=False):
            manager = SettingsManager(settings)
            self.assertTrue(manager.get_feature_flag("planner_v2", default=False))

    def test_validate_chat_schema_reports_invalid_ranges(self):
        settings = self._make_settings({
            "chat_default_max_tokens": "-1",
            "max_tool_rounds": "200",
            "feature_flags_json": '{"ok": true}',
        })
        manager = SettingsManager(settings)
        result = manager.validate_chat_schema()
        self.assertFalse(result["valid"])
        self.assertGreaterEqual(len(result["errors"]), 2)

    def test_validate_chat_schema_rejects_invalid_feature_flags_json(self):
        settings = self._make_settings({"feature_flags_json": "{invalid-json}"})
        manager = SettingsManager(settings)
        result = manager.validate_chat_schema()
        self.assertFalse(result["valid"])
        self.assertTrue(any("feature_flags_json" in err for err in result["errors"]))

    def test_get_planner_config_uses_feature_flags(self):
        settings = self._make_settings({
            "feature_flags_json": '{"planner_max_plan_steps": 5, "planner_financial_markers": ["yield", "dividend"]}',
        })
        manager = SettingsManager(settings)
        planner = manager.get_planner_config()
        self.assertEqual(planner["max_plan_steps"], 5)
        self.assertIn("yield", planner["financial_markers"])

    def test_validate_chat_schema_rejects_inverted_planner_thresholds(self):
        settings = self._make_settings({
            "feature_flags_json": '{"planner_complexity_high_threshold": 2, "planner_complexity_medium_threshold": 2}',
        })
        manager = SettingsManager(settings)
        result = manager.validate_chat_schema()
        self.assertFalse(result["valid"])
        self.assertTrue(any("planner_complexity_medium_threshold" in err for err in result["errors"]))

    def test_get_search_provider_config_uses_settings_and_flags(self):
        settings = self._make_settings(
            {
                "web_search_providers": "ddgs,wikipedia",
                "web_search_financial_domains": "reuters.com,ft.com",
                "web_search_max_results": 6,
                "feature_flags_json": (
                    '{"search_serpapi_enabled": true, '
                    '"search_sec_realtime_enabled": true, '
                    '"search_sec_user_agent": "CognitiveFolio/1.0 test@example.com", '
                    '"search_financial_provider_chain": ["serpapi", "sec_edgar"], '
                    '"search_query_refiner_enabled": true, '
                    '"search_result_reranker_enabled": true, '
                    '"search_result_reranker_top_k": 4, '
                    '"search_freshness_weighting_enabled": true, '
                    '"search_freshness_half_life_days": 28, '
                    '"search_cross_source_verifier_enabled": true, '
                    '"search_cross_source_min_sources": 2, '
                    '"search_cross_source_contradiction_penalty": 0.35, '
                    '"search_cross_source_confidence_boost": 0.25, '
                    '"search_domain_authority_enabled": true, '
                    '"search_domain_authority_default_weight": 0.15, '
                    '"search_domain_authority_weights": {"sec.gov": 1.1, "example.com": 0.4}, '
                    '"search_session_tracker_enabled": true, '
                    '"search_session_max_entries": 40, '
                    '"search_session_context_max_items": 4, '
                    '"search_session_context_max_chars": 220, '
                    '"search_session_followup_expand_enabled": true, '
                    '"search_semantic_search_enabled": true, '
                    '"search_semantic_embedding_dims": 128, '
                    '"search_semantic_score_weight": 0.85, '
                    '"search_trend_detector_enabled": true, '
                    '"search_trend_min_frequency": 3, '
                    '"search_trend_score_weight": 0.55, '
                    '"search_personalized_search_enabled": true, '
                    '"search_personalized_score_weight": 0.65, '
                    '"search_personalized_history_items": 7, '
                    '"search_preferred_sources": ["financial_news", "sec_edgar"], '
                    '"search_preferred_domains": ["reuters.com", "sec.gov"]}'
                ),
            }
        )
        manager = SettingsManager(settings)

        config = manager.get_search_provider_config()

        self.assertEqual(config["general_chain"], ["ddgs", "wikipedia"])
        self.assertEqual(config["financial_chain"], ["serpapi", "sec_edgar"])
        self.assertEqual(config["financial_domains"], ["reuters.com", "ft.com"])
        self.assertEqual(config["max_results"], 6)
        self.assertTrue(config["serpapi_enabled"])
        self.assertTrue(config["sec_realtime_enabled"])
        self.assertEqual(config["sec_user_agent"], "CognitiveFolio/1.0 test@example.com")
        self.assertTrue(config["query_refiner_enabled"])
        self.assertTrue(config["result_reranker_enabled"])
        self.assertEqual(config["result_reranker_top_k"], 4)
        self.assertTrue(config["freshness_weighting_enabled"])
        self.assertEqual(config["freshness_half_life_days"], 28)
        self.assertTrue(config["cross_source_verifier_enabled"])
        self.assertEqual(config["cross_source_min_sources"], 2)
        self.assertEqual(config["cross_source_contradiction_penalty"], 0.35)
        self.assertEqual(config["cross_source_confidence_boost"], 0.25)
        self.assertTrue(config["domain_authority_enabled"])
        self.assertEqual(config["domain_authority_default_weight"], 0.15)
        self.assertEqual(config["domain_authority_weights"], {"sec.gov": 1.1, "example.com": 0.4})
        self.assertTrue(config["session_tracker_enabled"])
        self.assertEqual(config["session_max_entries"], 40)
        self.assertEqual(config["session_context_max_items"], 4)
        self.assertEqual(config["session_context_max_chars"], 220)
        self.assertTrue(config["session_followup_expand_enabled"])
        self.assertTrue(config["semantic_search_enabled"])
        self.assertEqual(config["semantic_embedding_dims"], 128)
        self.assertEqual(config["semantic_score_weight"], 0.85)
        self.assertTrue(config["trend_detector_enabled"])
        self.assertEqual(config["trend_min_frequency"], 3)
        self.assertEqual(config["trend_score_weight"], 0.55)
        self.assertTrue(config["personalized_search_enabled"])
        self.assertEqual(config["personalized_score_weight"], 0.65)
        self.assertEqual(config["personalized_history_items"], 7)
        self.assertEqual(config["preferred_sources"], ["financial_news", "sec_edgar"])
        self.assertEqual(config["preferred_domains"], ["reuters.com", "sec.gov"])

    def test_get_performance_config_uses_feature_flags(self):
        settings = self._make_settings(
            {
                "feature_flags_json": (
                    '{"search_cache_enabled": true, '
                    '"search_cache_ttl_general_seconds": 1200, '
                    '"search_cache_ttl_financial_seconds": 240, '
                    '"search_cache_ttl_realtime_seconds": 90, '
                    '"content_summary_cache_enabled": true, '
                    '"content_summary_cache_ttl_seconds": 7200, '
                    '"tool_result_cache_enabled": true, '
                    '"tool_result_cache_ttl_seconds": 900, '
                    '"search_prefetch_enabled": true, '
                    '"search_prefetch_max_queries": 3, '
                    '"search_circuit_breaker_enabled": true, '
                    '"search_circuit_breaker_failure_threshold": 4, '
                    '"search_circuit_breaker_recovery_seconds": 300, '
                    '"search_circuit_breaker_half_open_calls": 2, '
                    '"search_rate_limiter_enabled": true, '
                    '"search_rate_limit_per_provider_per_minute": 45, '
                    '"search_stale_cache_fallback_enabled": true, '
                    '"db_batch_writer_enabled": true, '
                    '"db_index_maintenance_enabled": true, '
                    '"health_dashboard_enabled": true}'
                ),
            }
        )
        manager = SettingsManager(settings)

        config = manager.get_performance_config()

        self.assertTrue(config["search_cache_enabled"])
        self.assertEqual(config["search_cache_ttl_general_seconds"], 1200)
        self.assertEqual(config["search_cache_ttl_financial_seconds"], 240)
        self.assertEqual(config["search_cache_ttl_realtime_seconds"], 90)
        self.assertTrue(config["content_summary_cache_enabled"])
        self.assertEqual(config["content_summary_cache_ttl_seconds"], 7200)
        self.assertTrue(config["tool_result_cache_enabled"])
        self.assertEqual(config["tool_result_cache_ttl_seconds"], 900)
        self.assertTrue(config["search_prefetch_enabled"])
        self.assertEqual(config["search_prefetch_max_queries"], 3)
        self.assertTrue(config["search_circuit_breaker_enabled"])
        self.assertEqual(config["search_circuit_breaker_failure_threshold"], 4)
        self.assertEqual(config["search_circuit_breaker_recovery_seconds"], 300)
        self.assertEqual(config["search_circuit_breaker_half_open_calls"], 2)
        self.assertTrue(config["search_rate_limiter_enabled"])
        self.assertEqual(config["search_rate_limit_per_provider_per_minute"], 45)
        self.assertTrue(config["search_stale_cache_fallback_enabled"])
        self.assertTrue(config["db_batch_writer_enabled"])
        self.assertTrue(config["db_index_maintenance_enabled"])
        self.assertTrue(config["health_dashboard_enabled"])

    def test_validate_chat_schema_rejects_invalid_phase4_ttl_relationships(self):
        settings = self._make_settings(
            {
                "feature_flags_json": (
                    '{"search_cache_ttl_general_seconds": 120, '
                    '"search_cache_ttl_financial_seconds": 240, '
                    '"search_cache_ttl_realtime_seconds": 180}'
                )
            }
        )
        manager = SettingsManager(settings)

        result = manager.validate_chat_schema()

        self.assertFalse(result["valid"])
        self.assertTrue(any("search_cache_ttl_financial_seconds" in err for err in result["errors"]))
        self.assertTrue(any("search_cache_ttl_realtime_seconds" in err for err in result["errors"]))

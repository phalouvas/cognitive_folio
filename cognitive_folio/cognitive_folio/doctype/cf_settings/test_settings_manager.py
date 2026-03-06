from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from cognitive_folio.cognitive_folio.services.settings_manager import SettingsManager


class TestSettingsManager(FrappeTestCase):
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

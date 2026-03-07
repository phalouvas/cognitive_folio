# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

import unittest
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from cognitive_folio.cognitive_folio.doctype.cf_chat_message.cf_chat_message import (
    CFChatMessage,
    DEEPSEEK_CHAT_MAX_TOKENS_CAP,
)
from cognitive_folio.cognitive_folio.services.token_manager import TokenManager
from cognitive_folio.cognitive_folio.services.web_search_service import (
    FINANCIAL_QUERY_KEYWORDS,
    WebSearchService,
)


def _make_doc():
    """Create a minimal CFChatMessage instance without database access."""
    doc = CFChatMessage.__new__(CFChatMessage)
    doc.name = "test-msg-001"
    doc.chat = "test-chat-001"
    doc.model = "deepseek-chat"
    doc.prompt = "test prompt"
    doc.web_search = False
    doc.fetch_urls = False
    return doc


class TestCFChatMessageSearchHelpers(unittest.TestCase):
    """Unit tests for pure logic helper services and tool methods."""

    def test_count_markdown_results(self):
        token_manager = TokenManager(_make_doc())
        md = "1. First result\n2. Second result\n3. Third result"
        self.assertEqual(token_manager.count_markdown_search_results(md), 3)
        self.assertEqual(token_manager.count_markdown_search_results(""), 0)
        self.assertEqual(token_manager.count_markdown_search_results(None), 0)

    def test_classify_query_type(self):
        service = WebSearchService(_make_doc())
        self.assertEqual(service.classify_query_type("Apple AAPL stock earnings"), "financial")
        self.assertEqual(service.classify_query_type("how to cook pasta"), "general")
        self.assertEqual(service.classify_query_type(""), "general")

    def test_deduplicate_results(self):
        service = WebSearchService(_make_doc())
        deduped = service.deduplicate_results([
            {"url": "https://example.com/page/", "title": "A"},
            {"url": "https://example.com/page", "title": "A dup"},
            {"url": "", "title": "No URL"},
            {"url": "https://example.com/other", "title": "B"},
        ])
        self.assertEqual(len(deduped), 2)

    def test_tool_web_search_validation_and_providers_used(self):
        doc = _make_doc()
        service = WebSearchService(doc)
        doc._web_search_service = service

        with self.assertRaises(ValueError):
            doc._tool_web_search({"query": ""})

        with patch.object(service, "search_web_results", return_value=[{"source": "ddgs", "url": "https://a.com"}]):
            result = doc._tool_web_search({"query": "AAPL earnings"})
        self.assertIn("ddgs", result["providers_used"])

    def test_tool_search_financial_passes_ticker(self):
        doc = _make_doc()
        service = WebSearchService(doc)
        doc._web_search_service = service
        captured = {}

        def fake_search_financial_sources(**kwargs):
            captured.update(kwargs)
            return []

        with patch.object(service, "search_financial_sources", side_effect=fake_search_financial_sources):
            doc._tool_search_financial({"query": "Apple earnings", "ticker": "AAPL"})

        self.assertEqual(captured.get("ticker"), "AAPL")

    def test_search_web_results_auto_provider_selection(self):
        service = WebSearchService(_make_doc())
        service.prefetching.enabled = False
        service.search_compliance_tracker = MagicMock()
        service.access_control = MagicMock()
        service.access_control.has_access.return_value = True

        with patch.object(service.provider_registry, "resolve_chain", return_value=["ddgs", "wikipedia"]) as mock_resolve, patch.object(service, "_execute_provider_search", return_value=[]) as mock_exec:
            service.search_web_results("history of the Roman Empire")
        mock_resolve.assert_called_once_with(provider_hint="auto", query_type="general")
        providers = [call.kwargs.get("provider") for call in mock_exec.call_args_list]
        self.assertEqual(providers, ["ddgs", "wikipedia"])

        with patch.object(service.provider_registry, "resolve_chain", return_value=["ddgs", "sec_edgar"]) as mock_resolve, patch.object(service, "_execute_provider_search", return_value=[]) as mock_exec:
            service.search_web_results("Apple AAPL stock earnings 10-K")
        mock_resolve.assert_called_once_with(provider_hint="auto", query_type="financial")
        providers = [call.kwargs.get("provider") for call in mock_exec.call_args_list]
        self.assertEqual(providers, ["ddgs", "sec_edgar"])

    def test_search_financial_sources_routing(self):
        service = WebSearchService(_make_doc())
        service.prefetching.enabled = False
        service.search_compliance_tracker = MagicMock()
        service.access_control = MagicMock()
        service.access_control.has_access.return_value = True

        with patch.object(service.provider_registry, "resolve_chain", return_value=["ddgs", "sec_edgar", "financial_news"]) as mock_resolve, patch.object(service, "_execute_provider_search", return_value=[]) as mock_exec:
            service.search_financial_sources("Apple revenue", source="auto")
        mock_resolve.assert_called_once_with(provider_hint="auto", query_type="financial")
        providers = [call.kwargs.get("provider") for call in mock_exec.call_args_list]
        self.assertEqual(providers, ["ddgs", "sec_edgar", "financial_news"])

        service = WebSearchService(_make_doc())
        service.prefetching.enabled = False
        service.search_compliance_tracker = MagicMock()
        service.access_control = MagicMock()
        service.access_control.has_access.return_value = True
        with patch.object(service.provider_registry, "resolve_chain", return_value=["sec_edgar"]) as mock_resolve, patch.object(service, "_execute_provider_search", return_value=[]) as mock_exec:
            service.search_financial_sources("10-K", source="sec_edgar")
        mock_resolve.assert_called_once_with(provider_hint="sec_edgar", query_type="financial")
        providers = [call.kwargs.get("provider") for call in mock_exec.call_args_list]
        self.assertEqual(providers, ["sec_edgar"])

    def test_financial_keywords_constant(self):
        self.assertIsInstance(FINANCIAL_QUERY_KEYWORDS, frozenset)
        for term in ("stock", "earnings", "10-k", "sec", "edgar", "dividend"):
            self.assertIn(term, FINANCIAL_QUERY_KEYWORDS)

class TestCFChatMessageTokenAndThinkingModes(unittest.TestCase):
    def test_deepseek_chat_with_thinking_uses_chat_token_limits(self):
        doc = _make_doc()
        doc.model = "deepseek-chat"

        settings = MagicMock()

        def fake_get(fieldname):
            mapping = {
                "thinking_enabled": "1",
                "reasoner_default_max_tokens": "32000",
                "reasoner_max_tokens_cap": "64000",
                "chat_default_max_tokens": "7000",
                "chat_max_tokens_cap": "8000",
            }
            return mapping.get(fieldname)

        settings.get.side_effect = fake_get

        tokens = doc._get_max_completion_tokens(settings, "quick question")

        self.assertEqual(tokens, 7000)

    def test_deepseek_chat_tokens_hard_clamped_to_provider_limit(self):
        doc = _make_doc()
        doc.model = "deepseek-chat"

        settings = MagicMock()

        def fake_get(fieldname):
            mapping = {
                "chat_default_max_tokens": "50000",
                "chat_max_tokens_cap": "50000",
            }
            return mapping.get(fieldname)

        settings.get.side_effect = fake_get

        tokens = doc._get_max_completion_tokens(settings, "test")

        self.assertEqual(tokens, DEEPSEEK_CHAT_MAX_TOKENS_CAP)

    def test_thinking_mode_active_for_deepseek_chat_only_when_enabled(self):
        doc = _make_doc()
        doc.model = "deepseek-chat"

        settings = MagicMock()
        settings.get.return_value = "0"
        self.assertFalse(doc._is_thinking_mode_active(settings))

        settings.get.return_value = "1"
        self.assertTrue(doc._is_thinking_mode_active(settings))

    def test_thinking_mode_always_active_for_reasoner(self):
        doc = _make_doc()
        doc.model = "deepseek-reasoner"

        settings = MagicMock()
        settings.get.return_value = "0"

        self.assertTrue(doc._is_thinking_mode_active(settings))


class TestCFChatMessagePromptSensitivity(unittest.TestCase):
    def test_is_time_sensitive_prompt_for_weather(self):
        doc = _make_doc()
        self.assertTrue(doc._is_time_sensitive_prompt("What is the weather now in Larnaka Cyprus?"))

    def test_is_time_sensitive_prompt_for_geopolitical_timing(self):
        doc = _make_doc()
        self.assertTrue(doc._is_time_sensitive_prompt("How long will the war between Iran and Israel started in 2026 last?"))

    def test_is_time_sensitive_prompt_for_generic_finance(self):
        doc = _make_doc()
        self.assertFalse(doc._is_time_sensitive_prompt("Explain portfolio diversification principles."))


class _FakeEncoding:
    def encode(self, text):
        return list(str(text or ""))


class _FakeSettingsManager:
    def __init__(self, implicit_context_enabled=False, implicit_context_max_chars=320):
        self._implicit_context_enabled = implicit_context_enabled
        self._implicit_context_max_chars = implicit_context_max_chars

    def validate_chat_schema(self):
        return {"valid": True, "errors": []}

    def get_memory_config(self):
        return {"enabled": True}

    def get_feature_flag(self, fieldname, default=False):
        if fieldname == "implicit_chat_context_enabled":
            return self._implicit_context_enabled
        return default

    def get_int_config(self, fieldname, default, minimum=None, maximum=None):
        if fieldname == "implicit_chat_context_max_chars":
            value = self._implicit_context_max_chars
            if minimum is not None:
                value = max(value, minimum)
            if maximum is not None:
                value = min(value, maximum)
            return value
        return default


class TestCFChatMessageLifecycleFlows(unittest.TestCase):
    def test_implicit_context_injection_applies_for_security_plain_prompt(self):
        doc = _make_doc()
        doc.implicit_chat_context = 1
        security = SimpleNamespace(
            name="SEC-AAPL",
            symbol="AAPL",
            security_name="Apple Inc.",
            security_type="Stock",
            currency="USD",
        )

        injected_prompt, metadata = doc._inject_implicit_chat_context_if_needed(
            prompt_text="Give me your opinion of the company",
            original_prompt="Give me your opinion of the company",
            settings_manager=_FakeSettingsManager(implicit_context_enabled=True),
            portfolio=None,
            security=security,
        )

        self.assertTrue(metadata["enabled"])
        self.assertTrue(metadata["applied"])
        self.assertEqual(metadata["reason"], "applied")
        self.assertEqual(metadata["augmentation"], "implicit_security_context")
        self.assertEqual(metadata["enabled_source"], "message_checkbox")
        self.assertIn("Active security:", injected_prompt)
        self.assertIn("symbol=AAPL", injected_prompt)

    def test_implicit_context_injection_skips_when_template_tokens_present(self):
        doc = _make_doc()
        doc.implicit_chat_context = 1
        security = SimpleNamespace(name="SEC-AAPL", symbol="AAPL", security_name="Apple Inc.")

        injected_prompt, metadata = doc._inject_implicit_chat_context_if_needed(
            prompt_text="Give me your opinion for {{symbol}}",
            original_prompt="Give me your opinion for {{symbol}}",
            settings_manager=_FakeSettingsManager(implicit_context_enabled=True),
            portfolio=None,
            security=security,
        )

        self.assertEqual(injected_prompt, "Give me your opinion for {{symbol}}")
        self.assertTrue(metadata["enabled"])
        self.assertFalse(metadata["applied"])
        self.assertEqual(metadata["reason"], "explicit_template_tokens_present")

    def test_implicit_context_injection_respects_checkbox_off(self):
        doc = _make_doc()
        doc.implicit_chat_context = 0
        security = SimpleNamespace(name="SEC-AAPL", symbol="AAPL", security_name="Apple Inc.")

        injected_prompt, metadata = doc._inject_implicit_chat_context_if_needed(
            prompt_text="Give me your opinion of the company",
            original_prompt="Give me your opinion of the company",
            settings_manager=_FakeSettingsManager(implicit_context_enabled=True),
            portfolio=None,
            security=security,
        )

        self.assertEqual(injected_prompt, "Give me your opinion of the company")
        self.assertFalse(metadata["enabled"])
        self.assertEqual(metadata["enabled_source"], "message_checkbox")
        self.assertEqual(metadata["reason"], "disabled")

    def test_detach_noncritical_links_clears_all_supported_doctypes(self):
        doc = _make_doc()

        with patch("frappe.db.exists", return_value=True) as mock_exists, patch("frappe.db.set_value") as mock_set_value:
            doc._detach_noncritical_links()

        expected_targets = {
            ("CF Tool Metric", "last_message"),
            ("CF Quality Metric", "last_message"),
            ("CF Experiment Metric", "chat_message"),
            ("CF Monitoring Alert", "chat_message"),
            ("CF Access Audit", "chat_message"),
            ("CF Search Compliance Log", "chat_message"),
        }
        self.assertEqual(mock_exists.call_count, len(expected_targets))
        self.assertEqual(mock_set_value.call_count, len(expected_targets))

        observed_targets = {
            (args[0], args[2])
            for args, _kwargs in [
                (call.args, call.kwargs)
                for call in mock_set_value.call_args_list
            ]
        }
        self.assertEqual(observed_targets, expected_targets)

    def test_process_in_background_marks_success_and_publishes_event(self):
        trigger_doc = _make_doc()
        trigger_doc._publish_chat_realtime = MagicMock()

        message_doc = MagicMock()
        message_doc.name = trigger_doc.name
        message_doc.chat = trigger_doc.chat
        message_doc._get_performance_config.return_value = {"db_batch_writer_enabled": False}

        with patch("frappe.get_doc", return_value=message_doc), patch("frappe.db.commit"):
            trigger_doc.process_in_background()

        message_doc.send.assert_called_once()
        message_doc.db_set.assert_any_call("status", "Processing", update_modified=False)
        message_doc.db_set.assert_any_call("status", "Success", update_modified=False)
        message_doc.db_update.assert_called_once()

        trigger_doc._publish_chat_realtime.assert_called_once()
        publish_payload = trigger_doc._publish_chat_realtime.call_args.kwargs["payload"]
        self.assertEqual(publish_payload["status"], "success")
        self.assertEqual(publish_payload["message_id"], trigger_doc.name)

    def test_process_in_background_failure_marks_failed_and_publishes_error(self):
        trigger_doc = _make_doc()
        trigger_doc._publish_chat_realtime = MagicMock()

        message_doc = MagicMock()
        message_doc.name = trigger_doc.name
        message_doc.chat = trigger_doc.chat
        message_doc._get_performance_config.return_value = {"db_batch_writer_enabled": False}
        message_doc.send.side_effect = RuntimeError("boom")

        with patch("frappe.get_doc", return_value=message_doc), patch("frappe.db.commit"), patch("frappe.log_error"):
            trigger_doc.process_in_background()

        message_doc.db_set.assert_any_call("status", "Processing", update_modified=False)
        message_doc.db_set.assert_any_call("status", "Failed", update_modified=False)
        message_doc.db_update.assert_called_once()

        trigger_doc._publish_chat_realtime.assert_called_once()
        publish_payload = trigger_doc._publish_chat_realtime.call_args.kwargs["payload"]
        self.assertEqual(publish_payload["status"], "error")
        self.assertEqual(publish_payload["message_id"], trigger_doc.name)

    def test_send_populates_runtime_audit_with_tool_metadata(self):
        doc = _make_doc()
        doc.system_prompt = ""
        doc.prompt = "What is the weather now in Larnaka Cyprus?"
        doc.web_search = True
        doc.db_update = MagicMock()

        settings = MagicMock()
        settings.system_content = "You are a helpful assistant."
        settings.open_ai_url = "https://example.test"
        settings.get_password.return_value = "test-key"

        chat_doc = SimpleNamespace(name=doc.chat, portfolio=None, security=None)
        fake_tiktoken = SimpleNamespace(
            encoding_for_model=lambda _model: _FakeEncoding(),
            get_encoding=lambda _name: _FakeEncoding(),
        )
        fake_openai = SimpleNamespace(OpenAI=lambda **_kwargs: MagicMock())

        tool_usage = {
            "tool_rounds": 2,
            "plan": {"steps": [{"tool": "web_search"}]},
            "tool_metrics": {"web_search": {"success_rate": 1.0}},
            "tool_metrics_store": {"stored": True},
            "tool_execution": {"forced_realtime_web_search": True},
        }
        tool_trace = [
            {
                "tool": "web_search",
                "success": True,
                "duration_ms": 32,
                "result": {"count": 1},
            }
        ]

        fake_orchestrator = MagicMock()
        fake_orchestrator.run_tool_call_chain.return_value = (
            "Realtime answer grounded in sources.",
            "",
            "stop",
            tool_usage,
            tool_trace,
        )

        fake_memory_manager = MagicMock()
        fake_memory_manager.get_context_for_prompt.return_value = ""
        fake_memory_manager.record_turn.return_value = {"stored": True}

        fake_metrics_collector = MagicMock()
        fake_metrics_collector.persist_quality_metric.return_value = {"created": True}

        fake_realtime_metrics = MagicMock()

        compliance_cfg = {
            "audit_logging_enabled": False,
            "ab_testing_enabled": False,
            "content_sanitizer_enabled": False,
            "privacy_preserver_enabled": False,
            "quality_scoring_enabled": False,
            "cost_optimizer_enabled": False,
            "alerting_enabled": False,
        }

        original_get_doc = frappe.get_doc

        def _fake_get_doc(doctype, *args, **kwargs):
            if doctype == "CF Chat":
                return chat_doc
            return original_get_doc(doctype, *args, **kwargs)

        with patch.dict(sys.modules, {"openai": fake_openai, "tiktoken": fake_tiktoken}), patch(
            "frappe.get_doc", side_effect=_fake_get_doc
        ), patch("frappe.get_single", return_value=settings), patch("frappe.get_all", return_value=[]), patch(
            "frappe.db.commit"
        ), patch("frappe.utils.nowdate", return_value="2026-03-07"):
            doc._get_settings_manager = MagicMock(return_value=_FakeSettingsManager())
            doc._get_compliance_monitoring_config = MagicMock(return_value=compliance_cfg)
            doc._get_prompt_processor = MagicMock(return_value=SimpleNamespace(
                prepare_prompt_without_mutation=lambda prompt, _portfolio, _security: prompt,
                embed_url_content=lambda prompt: prompt,
                extract_pdf_text_for_prompt=lambda prompt: prompt,
            ))
            doc._get_tool_orchestrator = MagicMock(return_value=fake_orchestrator)
            doc._get_memory_manager = MagicMock(return_value=fake_memory_manager)
            doc._get_metrics_collector = MagicMock(return_value=fake_metrics_collector)
            doc._get_realtime_metrics = MagicMock(return_value=fake_realtime_metrics)
            doc._get_experiment_manager = MagicMock()
            doc._get_quality_scorer = MagicMock()
            doc._get_cost_optimizer = MagicMock()
            doc._get_alerting_system = MagicMock()
            doc._get_content_sanitizer = MagicMock()
            doc._get_privacy_preserver = MagicMock()
            doc._get_audit_logger = MagicMock()
            doc._conversation_summarization_enabled = MagicMock(return_value=False)
            doc._get_max_context_tokens = MagicMock(return_value=120000)
            doc._get_max_completion_tokens = MagicMock(return_value=4096)

            doc.send()

        self.assertEqual(doc.response, "Realtime answer grounded in sources.")
        self.assertEqual(doc.tokens["tool_calls_count"], 1)
        self.assertEqual(doc.runtime_audit["tools"]["rounds"], 2)
        self.assertEqual(doc.runtime_audit["tools"]["calls"], 1)
        self.assertEqual(doc.runtime_audit["tools"]["names"], ["web_search"])
        self.assertEqual(doc.runtime_audit["web_search"]["search_iterations"], 1)
        self.assertFalse(doc.runtime_audit["context_injection"]["applied"])
        self.assertTrue(doc.runtime_audit["memory"]["recorded"])
        doc.db_update.assert_called_once()
        fake_realtime_metrics.publish.assert_called_once()

    def test_send_applies_implicit_context_for_linked_security_when_enabled(self):
        doc = _make_doc()
        doc.implicit_chat_context = 1
        doc.system_prompt = ""
        doc.prompt = "Give me your opinion of the company"
        doc.web_search = False
        doc.db_update = MagicMock()

        settings = MagicMock()
        settings.system_content = "You are a helpful assistant."
        settings.open_ai_url = "https://example.test"
        settings.get_password.return_value = "test-key"

        security_doc = SimpleNamespace(
            name="SEC-AAPL",
            symbol="AAPL",
            security_name="Apple Inc.",
            security_type="Stock",
            currency="USD",
            ai_modified=None,
            save=MagicMock(),
        )
        chat_doc = SimpleNamespace(name=doc.chat, portfolio=None, security="SEC-AAPL")
        fake_tiktoken = SimpleNamespace(
            encoding_for_model=lambda _model: _FakeEncoding(),
            get_encoding=lambda _name: _FakeEncoding(),
        )
        fake_openai = SimpleNamespace(OpenAI=lambda **_kwargs: MagicMock())

        captured = {}

        def _run_tool_chain(**kwargs):
            captured["messages"] = kwargs.get("messages") or []
            return (
                "Opinion response.",
                "",
                "stop",
                {"tool_rounds": 0},
                [],
            )

        fake_orchestrator = MagicMock()
        fake_orchestrator.run_tool_call_chain.side_effect = _run_tool_chain

        fake_memory_manager = MagicMock()
        fake_memory_manager.get_context_for_prompt.return_value = ""
        fake_memory_manager.record_turn.return_value = {"stored": True}

        fake_metrics_collector = MagicMock()
        fake_metrics_collector.persist_quality_metric.return_value = {"created": True}

        fake_realtime_metrics = MagicMock()

        compliance_cfg = {
            "audit_logging_enabled": False,
            "ab_testing_enabled": False,
            "content_sanitizer_enabled": False,
            "privacy_preserver_enabled": False,
            "quality_scoring_enabled": False,
            "cost_optimizer_enabled": False,
            "alerting_enabled": False,
        }

        original_get_doc = frappe.get_doc

        def _fake_get_doc(doctype, *args, **kwargs):
            if doctype == "CF Chat":
                return chat_doc
            if doctype == "CF Security":
                return security_doc
            return original_get_doc(doctype, *args, **kwargs)

        with patch.dict(sys.modules, {"openai": fake_openai, "tiktoken": fake_tiktoken}), patch(
            "frappe.get_doc", side_effect=_fake_get_doc
        ), patch("frappe.get_single", return_value=settings), patch("frappe.get_all", return_value=[]), patch(
            "frappe.db.commit"
        ), patch("frappe.utils.nowdate", return_value="2026-03-07"):
            doc._get_settings_manager = MagicMock(
                return_value=_FakeSettingsManager(implicit_context_enabled=True)
            )
            doc._get_compliance_monitoring_config = MagicMock(return_value=compliance_cfg)
            doc._get_prompt_processor = MagicMock(return_value=SimpleNamespace(
                prepare_prompt_without_mutation=lambda prompt, _portfolio, _security: prompt,
                embed_url_content=lambda prompt: prompt,
                extract_pdf_text_for_prompt=lambda prompt: prompt,
            ))
            doc._get_tool_orchestrator = MagicMock(return_value=fake_orchestrator)
            doc._get_memory_manager = MagicMock(return_value=fake_memory_manager)
            doc._get_metrics_collector = MagicMock(return_value=fake_metrics_collector)
            doc._get_realtime_metrics = MagicMock(return_value=fake_realtime_metrics)
            doc._get_experiment_manager = MagicMock()
            doc._get_quality_scorer = MagicMock()
            doc._get_cost_optimizer = MagicMock()
            doc._get_alerting_system = MagicMock()
            doc._get_content_sanitizer = MagicMock()
            doc._get_privacy_preserver = MagicMock()
            doc._get_audit_logger = MagicMock()
            doc._conversation_summarization_enabled = MagicMock(return_value=False)
            doc._get_max_context_tokens = MagicMock(return_value=120000)
            doc._get_max_completion_tokens = MagicMock(return_value=4096)

            doc.send()

        self.assertTrue(doc.runtime_audit["context_injection"]["applied"])
        self.assertEqual(doc.runtime_audit["context_injection"]["augmentation"], "implicit_security_context")
        self.assertIn("implicit_security_context", doc.runtime_audit["augmentations"])
        last_message = captured["messages"][-1]["content"]
        self.assertIn("Active security:", last_message)
        self.assertIn("symbol=AAPL", last_message)

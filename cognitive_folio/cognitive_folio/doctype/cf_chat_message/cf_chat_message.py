import frappe
from frappe.model.document import Document
import re
import time
import json
from functools import lru_cache
from cognitive_folio.cognitive_folio.services import (
	AccessControl,
	AlertingSystem,
	AnswerQualityScorer,
	AuditLogger,
	MemoryManager,
	BatchDatabaseWriter,
	CostOptimizer,
	ContentSummarizationCache,
	ContentSanitizer,
	ExperimentManager,
	MetricsCollector,
	PrivacyPreserver,
	PromptProcessor,
	RealTimeMetrics,
	SettingsManager,
	TokenManager,
	ToolResultCache,
	ToolRegistry,
	ToolOrchestrator,
	WebSearchService,
)
from cognitive_folio.utils.markdown import safe_markdown_to_html
from cognitive_folio.utils.helper import replace_variables, expand_financials_variable, expand_edgar_section_variable
from cognitive_folio.utils.url_fetcher import fetch_and_embed_url_content


MAX_CONTEXT_TOKENS = 120000
DEFAULT_CHAT_MAX_TOKENS = 4000
DEFAULT_REASONER_MAX_TOKENS = 32000
MAX_CHAT_MAX_TOKENS = 8000
MAX_REASONER_MAX_TOKENS = 64000
DEEPSEEK_CHAT_MAX_TOKENS_CAP = 8192
MAX_OPENAI_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 1.5
DEFAULT_MAX_TOOL_ROUNDS = 8
DEFAULT_MAX_TOOL_CALLS_PER_ROUND = 8
DEFAULT_TOOL_RESULT_MAX_CHARS = 8000
DEFAULT_THINKING_BUDGET_TOKENS = 2048
DEFAULT_THINKING_TYPE = "reasoning"
DEFAULT_TOP_P = 1.0
DEFAULT_FREQUENCY_PENALTY = 0.0
DEFAULT_PRESENCE_PENALTY = 0.0

class CFChatMessage(Document):
	def _detach_noncritical_links(self):
		"""Detach analytics links that should not block message lifecycle actions."""
		link_targets = [
			("CF Tool Metric", "last_message"),
			("CF Quality Metric", "last_message"),
			("CF Experiment Metric", "chat_message"),
			("CF Monitoring Alert", "chat_message"),
			("CF Access Audit", "chat_message"),
			("CF Search Compliance Log", "chat_message"),
		]
		for doctype, fieldname in link_targets:
			if not frappe.db.exists("DocType", doctype):
				continue
			frappe.db.set_value(
				doctype,
				{fieldname: self.name},
				fieldname,
				None,
				update_modified=False,
			)

	def on_trash(self):
		"""Detach non-critical analytics links so message deletion succeeds."""
		try:
			self._detach_noncritical_links()
		except Exception:
			frappe.log_error(title="CFChatMessage on_trash cleanup failed", message=frappe.get_traceback())

	def on_cancel(self):
		"""Detach non-critical analytics links so message cancellation succeeds."""
		try:
			self._detach_noncritical_links()
		except Exception:
			frappe.log_error(title="CFChatMessage on_cancel cleanup failed", message=frappe.get_traceback())

	def _get_prompt_processor(self):
		if not hasattr(self, "_prompt_processor"):
			self._prompt_processor = PromptProcessor(self)
		return self._prompt_processor

	def _get_token_manager(self):
		if not hasattr(self, "_token_manager"):
			self._token_manager = TokenManager(self)
		return self._token_manager

	def _get_tool_orchestrator(self):
		if not hasattr(self, "_tool_orchestrator"):
			self._tool_orchestrator = ToolOrchestrator(self)
		return self._tool_orchestrator

	def _get_web_search_service(self):
		if not hasattr(self, "_web_search_service"):
			self._web_search_service = WebSearchService(self)
		return self._web_search_service

	def _get_tool_registry(self):
		if not hasattr(self, "_tool_registry"):
			self._tool_registry = ToolRegistry(self)
		return self._tool_registry

	def _get_settings_manager(self, settings):
		return SettingsManager(settings)

	def _get_memory_manager(self):
		if not hasattr(self, "_memory_manager"):
			self._memory_manager = MemoryManager(self)
		return self._memory_manager

	def _get_performance_config(self):
		if hasattr(self, "_performance_config"):
			return self._performance_config

		try:
			settings = frappe.get_cached_doc("CF Settings")
			self._performance_config = self._get_settings_manager(settings).get_performance_config()
		except Exception:
			self._performance_config = {}

		runtime_id = str(getattr(self, "chat", None) or getattr(self, "name", None) or "default")
		suffix = runtime_id.replace(" ", "_")
		self._performance_config.setdefault("tool_result_cache_namespace", f"cf:tool:{suffix}")
		self._performance_config.setdefault("content_summary_cache_namespace", f"cf:content:{suffix}")

		return self._performance_config

	def _get_tool_result_cache(self):
		if not hasattr(self, "_tool_result_cache"):
			self._tool_result_cache = ToolResultCache(config=self._get_performance_config())
		return self._tool_result_cache

	def _get_content_summarization_cache(self):
		if not hasattr(self, "_content_summarization_cache"):
			self._content_summarization_cache = ContentSummarizationCache(config=self._get_performance_config())
		return self._content_summarization_cache

	def _get_compliance_monitoring_config(self, settings=None):
		if hasattr(self, "_compliance_monitoring_config"):
			return self._compliance_monitoring_config

		settings_doc = settings or frappe.get_cached_doc("CF Settings")
		self._compliance_monitoring_config = self._get_settings_manager(settings_doc).get_compliance_monitoring_config()
		return self._compliance_monitoring_config

	def _get_access_control(self):
		if not hasattr(self, "_access_control"):
			self._access_control = AccessControl()
		return self._access_control

	def _get_audit_logger(self):
		if not hasattr(self, "_audit_logger"):
			self._audit_logger = AuditLogger()
		return self._audit_logger

	def _get_content_sanitizer(self):
		if not hasattr(self, "_content_sanitizer"):
			self._content_sanitizer = ContentSanitizer()
		return self._content_sanitizer

	def _get_privacy_preserver(self):
		if not hasattr(self, "_privacy_preserver"):
			self._privacy_preserver = PrivacyPreserver()
		return self._privacy_preserver

	def _get_quality_scorer(self):
		if not hasattr(self, "_quality_scorer"):
			self._quality_scorer = AnswerQualityScorer()
		return self._quality_scorer

	def _get_cost_optimizer(self):
		if not hasattr(self, "_cost_optimizer"):
			self._cost_optimizer = CostOptimizer()
		return self._cost_optimizer

	def _get_metrics_collector(self):
		if not hasattr(self, "_metrics_collector"):
			self._metrics_collector = MetricsCollector()
		return self._metrics_collector

	def _get_experiment_manager(self):
		if not hasattr(self, "_experiment_manager"):
			self._experiment_manager = ExperimentManager()
		return self._experiment_manager

	def _get_alerting_system(self):
		if not hasattr(self, "_alerting_system"):
			self._alerting_system = AlertingSystem()
		return self._alerting_system

	def _get_realtime_metrics(self):
		if not hasattr(self, "_realtime_metrics"):
			self._realtime_metrics = RealTimeMetrics()
		return self._realtime_metrics

	def _publish_chat_realtime(self, event_name, payload):
		"""Publish realtime updates to related doc rooms."""

		chat_id = payload.get("chat_id")
		if chat_id:
			frappe.publish_realtime(
				event=event_name,
				message=payload,
				doctype="CF Chat",
				docname=chat_id,
			)

		message_id = payload.get("message_id")
		if message_id:
			frappe.publish_realtime(
				event=event_name,
				message=payload,
				doctype="CF Chat Message",
				docname=message_id,
			)

	def validate(self):
		if not self.system_prompt:
			chat = frappe.get_doc("CF Chat", self.chat)
			if chat.system_prompt:
				self.system_prompt = chat.system_prompt

	@frappe.whitelist()
	def process(self):
		# Skip processing if this is a duplicated message
		if getattr(self.flags, 'ignore_before_save', False):
			return
			
		self.status = "Processing"
		
		self.response = "Processing your request..."
		self.response_html = safe_markdown_to_html(self.response)
		self.save()
		
		# Enqueue the job to run after the document is saved
		frappe.db.commit()
		frappe.enqueue(
			method=self.process_in_background,
			queue="long",
			timeout=1800,
			now=False,
			job_id=f"chat_message_{self.name}"
		)

	def process_in_background(self):
		try:			
			# Reload the document from the database
			message_doc = frappe.get_doc("CF Chat Message", self.name)
			performance_config = message_doc._get_performance_config()
			batch_enabled = bool(performance_config.get("db_batch_writer_enabled", True))
			batch_writer = BatchDatabaseWriter() if batch_enabled else None
			
			# Update status to processing
			if batch_writer:
				batch_writer.add_set_value("CF Chat Message", message_doc.name, "status", "Processing", update_modified=False)
				batch_writer.flush(commit=True)
			else:
				message_doc.db_set("status", "Processing", update_modified=False)
				frappe.db.commit()
			
			# Process the message (use the reloaded document)
			message_doc.send()
			
			# Update status to success and save the response
			if batch_writer:
				message_doc.status = "Success"
				batch_writer.add_doc_update(message_doc)
				batch_writer.flush(commit=True)
			else:
				message_doc.db_set("status", "Success", update_modified=False)
				message_doc.db_update()
				frappe.db.commit()
			
			# Notify the user that the response is ready
			self._publish_chat_realtime(
				event_name='cf_job_completed',
				payload={
					'message_id': message_doc.name,
					'chat_id': message_doc.chat,
					'status': 'success',
					'message': f"Response ready for message {message_doc.name}"
				}
			)
		except Exception as e:
			error_message = str(e)
			frappe.log_error(title=f"Chat Message Processing Error: {self.name}", message=error_message)
			
			try:
				# Reload the document and update it with error
				message_doc = frappe.get_doc("CF Chat Message", self.name)
				message_doc.response = f"Error processing request: {error_message}"
				message_doc.response_html = safe_markdown_to_html(message_doc.response)
				message_doc.db_set("status", "Failed", update_modified=False)
				message_doc.db_update()
				frappe.db.commit()
			except Exception as inner_e:
				# Log the inner exception but continue to notification
				frappe.log_error(title=f"Failed to update chat message with error: {self.name}", 
							   message=f"Original error: {error_message}\nUpdate error: {str(inner_e)}")
				# Set status to failed even if update fails
				try:
					frappe.db.set_value("CF Chat Message", self.name, "status", "Failed", update_modified=False)
					frappe.db.commit()
				except:
					pass
			
			# Always try to notify user about the error - moved outside the inner try block
			try:
				self._publish_chat_realtime(
					event_name='cf_job_completed',
					payload={
						'message_id': self.name,
						'chat_id': getattr(message_doc, 'chat', self.chat),
						'status': 'error',
						'message': f"Error processing message {self.name}: {error_message}"
					}
				)
			except Exception as notify_e:
				# Last resort - log that we couldn't even notify the user
				frappe.log_error(title=f"Failed to notify user of chat error: {self.name}", 
							   message=f"Original error: {error_message}\nNotification error: {str(notify_e)}")

	def send(self):
		request_started_at = time.time()

		try:
			from openai import OpenAI
			import tiktoken
		except ImportError:
			frappe.throw("OpenAI package is not installed. Please run 'bench pip install openai'")
			return 0
		
		chat = frappe.get_doc("CF Chat", self.chat)
		portfolio = None
		if chat.portfolio:
			portfolio = frappe.get_doc("CF Portfolio", chat.portfolio)
		security = None
		if chat.security:
			security = frappe.get_doc("CF Security", chat.security)
			security.ai_modified = frappe.utils.now_datetime().strftime('%Y-%m-%d %H:%M:%S')
			security.save()
		settings = frappe.get_single("CF Settings")
		settings_manager = self._get_settings_manager(settings)
		compliance_monitoring_config = self._get_compliance_monitoring_config(settings)
		validation = settings_manager.validate_chat_schema()
		if not validation.get("valid"):
			frappe.logger("cognitive_folio").warning(
				"CF Settings validation issues for %s: %s",
				self.name,
				"; ".join(validation.get("errors", [])),
			)
		client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
		if compliance_monitoring_config.get("audit_logging_enabled", True):
			self._get_audit_logger().log(
				event_name="chat_send_started",
				status="success",
				details={"model": self.model},
				chat=self.chat,
				message=self.name,
			)
		runtime_audit = {
			"model": self.model,
			"augmentations": [],
			"memory": {
				"enabled": False,
				"used": False,
				"context_chars": 0,
				"recorded": False,
			},
			"web_search": {
				"enabled": bool(getattr(self, "web_search", False)),
				"query": None,
				"results_count": 0,
				"fallback": None,
				"providers_used": [],
				"search_iterations": 0,
				"financial_searches": 0,
			},
			"tools": {
				"enabled": True,
				"rounds": 0,
				"calls": 0,
				"names": [],
			},
		}
		experiment_assignment = {"experiment": None, "variant": "control"}
		if compliance_monitoring_config.get("ab_testing_enabled", True):
			experiment_assignment = self._get_experiment_manager().assign_variant(chat.name)
		runtime_audit["experiment"] = experiment_assignment
	
		# Initialize tokenizer for the model
		try:
			encoding = tiktoken.encoding_for_model(self.model)
		except KeyError:
			# Fallback to a common encoding if model not found
			encoding = tiktoken.get_encoding("cl100k_base")
	
		messages = [
			{"role": "system", "content": self.system_prompt if self.system_prompt else settings.system_content}
		]
	
		# Add previous messages from the chat with token management
		chat_messages = frappe.get_all(
			"CF Chat Message",
			filters={
				"chat": chat.name,
				"name": ["!=", self.name]  # Exclude the current message
			},
			fields=["prompt", "response"],
			order_by="creation desc"  # Get most recent messages first
		)
		
		# Calculate tokens for system message and reserve space for current prompt
		system_tokens = len(encoding.encode(messages[0]["content"]))
		max_context_tokens = self._get_max_context_tokens(settings)  # Leave buffer for response
		available_tokens = max_context_tokens - system_tokens
		
		original_prompt = self.prompt or ""

		# Build runtime model prompt while preserving original user prompt
		runtime_prompt = self._get_prompt_processor().prepare_prompt_without_mutation(original_prompt, portfolio, security)
		if compliance_monitoring_config.get("privacy_preserver_enabled", True):
			runtime_prompt = self._get_privacy_preserver().anonymize_query(runtime_prompt)
		if runtime_prompt != original_prompt:
			runtime_audit["augmentations"].append("template_variables")

		# Detect URLs and embed their content (guarded by optional checkbox)
		if getattr(self, 'fetch_urls', False):
			try:
				before_prompt = runtime_prompt
				runtime_prompt = self._get_prompt_processor().embed_url_content(runtime_prompt)
				if runtime_prompt != before_prompt:
					runtime_audit["augmentations"].append("url_content")
			except Exception as e:
				frappe.log_error(f"URL embedding failed for message {self.name}: {str(e)}", "URL Fetch Error")
		
		# Extract PDF text and tables, convert to markdown if available
		try:
			before_prompt = runtime_prompt
			runtime_prompt = self._get_prompt_processor().extract_pdf_text_for_prompt(runtime_prompt)
			if runtime_prompt != before_prompt:
				runtime_audit["augmentations"].append("pdf_extraction")
		except Exception as e:
			frappe.log_error(f"PDF extraction failed for message {self.name}: {str(e)}", "PDF Extraction Error")
		
		if compliance_monitoring_config.get("content_sanitizer_enabled", True):
			runtime_prompt = self._get_content_sanitizer().sanitize_text(runtime_prompt)

		# Web search is tool-only. No pre-tool prompt augmentation path.
    
		current_prompt_tokens = len(encoding.encode(runtime_prompt or ""))
		available_tokens -= current_prompt_tokens
		
		overflow_messages = []

		# Add previous messages while staying within token limit
		used_tokens = 0
		for idx, message in enumerate(chat_messages):  # Already ordered in most recent first order
			user_tokens = len(encoding.encode(message.prompt or ""))
			assistant_tokens = len(encoding.encode(message.response or ""))
			message_tokens = user_tokens + assistant_tokens
			
			if used_tokens + message_tokens > available_tokens:
				overflow_messages = chat_messages[idx:]
				break  # Stop adding messages if we exceed token limit
				
			# Insert at position 1 to maintain chronological order (after system message)
			messages.insert(1, {"role": "user", "content": message.prompt or ""})
			messages.insert(2, {"role": "assistant", "content": message.response or ""})
			used_tokens += message_tokens

		if overflow_messages and self._conversation_summarization_enabled(settings):
			summary = self._get_token_manager().summarize_conversation(overflow_messages)
			if summary:
				messages.insert(1, {
					"role": "system",
					"content": f"Summary of earlier conversation context:\n{summary}",
				})

		memory_manager = self._get_memory_manager()
		memory_context = memory_manager.get_context_for_prompt(
			chat_name=chat.name,
			settings_manager=settings_manager,
			current_prompt=runtime_prompt,
			context={
				"portfolio": getattr(portfolio, "name", None) if portfolio else None,
				"security": getattr(security, "name", None) if security else None,
			},
		)
		runtime_audit["memory"]["enabled"] = bool(settings_manager.get_memory_config().get("enabled", True))
		if memory_context:
			messages.insert(1, {
				"role": "system",
				"content": f"Conversation memory:\n{memory_context}",
			})
			runtime_audit["memory"]["used"] = True
			runtime_audit["memory"]["context_chars"] = len(memory_context)

		# DeepSeek multi-turn guideline: clear prior reasoning content before a new user turn.
		messages = self._get_token_manager().clear_reasoning_content(messages)
		
		# Add current message
		messages.append({"role": "user", "content": runtime_prompt})

		full_response, reasoning_content, finish_reason, usage_summary, tool_trace = self._get_tool_orchestrator().run_tool_call_chain(
			client=client,
			messages=messages,
			settings=settings,
			chat=chat,
			portfolio=portfolio,
			security=security,
		)

		if compliance_monitoring_config.get("content_sanitizer_enabled", True):
			full_response = self._get_content_sanitizer().sanitize_text(full_response)

		self.response = full_response
		self.response_html = safe_markdown_to_html(full_response)
		self.reasoning = reasoning_content

		total_duration_seconds = round(time.time() - request_started_at, 3)
		response_tokens = len(encoding.encode(full_response or ""))
		prompt_tokens = current_prompt_tokens + system_tokens + used_tokens
		total_tokens = prompt_tokens + response_tokens

		base_tokens = {
			"prompt_tokens": prompt_tokens,
			"completion_tokens": response_tokens,
			"total_tokens": total_tokens,
		}
		if isinstance(usage_summary, dict):
			base_tokens.update(usage_summary)

		base_tokens.update({
			"model": self.model,
			"finish_reason": finish_reason,
			"duration_seconds": total_duration_seconds,
			"max_tokens": self._get_max_completion_tokens(settings),
			"tool_calls_enabled": True,
			"tool_calls_count": len(tool_trace),
			"tool_calls_trace": tool_trace,
			"prompt_augmented": bool(runtime_prompt != original_prompt),
			"prompt_original_length": len(original_prompt or ""),
			"prompt_runtime_length": len(runtime_prompt or ""),
		})

		self.tokens = base_tokens
		runtime_audit["tools"]["rounds"] = int((usage_summary or {}).get("tool_rounds", 0) or 0) if isinstance(usage_summary, dict) else 0
		runtime_audit["tools"]["calls"] = len(tool_trace or [])
		runtime_audit["tools"]["names"] = sorted({(item or {}).get("tool") for item in (tool_trace or []) if (item or {}).get("tool")})
		runtime_audit["tools"]["plan"] = (usage_summary or {}).get("plan") if isinstance(usage_summary, dict) else None
		runtime_audit["tools"]["metrics"] = (usage_summary or {}).get("tool_metrics") if isinstance(usage_summary, dict) else None
		runtime_audit["tools"]["metrics_store"] = (usage_summary or {}).get("tool_metrics_store") if isinstance(usage_summary, dict) else None
		runtime_audit["tools"]["execution"] = (usage_summary or {}).get("tool_execution") if isinstance(usage_summary, dict) else None
		runtime_audit["prompt_augmented"] = bool(runtime_prompt != original_prompt)
		# Track tool-driven search provenance
		search_tool_calls = [t for t in (tool_trace or []) if (t or {}).get("tool") in ("web_search", "search_financial")]
		runtime_audit["web_search"]["search_iterations"] = len(search_tool_calls)
		runtime_audit["web_search"]["financial_searches"] = sum(
			1 for t in (tool_trace or []) if (t or {}).get("tool") == "search_financial"
		)

		memory_record_result = memory_manager.record_turn(
			chat_name=chat.name,
			prompt=original_prompt,
			response=full_response,
			settings_manager=settings_manager,
			context={
				"portfolio": getattr(portfolio, "name", None) if portfolio else None,
				"security": getattr(security, "name", None) if security else None,
			},
		)
		runtime_audit["memory"]["recorded"] = bool((memory_record_result or {}).get("stored"))
		runtime_audit["memory"]["record"] = memory_record_result

		quality_scores = {"quality_score": 0.0, "relevance_score": 0.0, "completeness_score": 0.0, "grounding_score": 0.0}
		if compliance_monitoring_config.get("quality_scoring_enabled", True):
			quality_scores = self._get_quality_scorer().score(original_prompt, full_response, tool_trace=tool_trace)

		cost_metrics = {"estimated_cost_usd": 0.0, "tool_calls": len(tool_trace or []), "recommendation": "n/a"}
		if compliance_monitoring_config.get("cost_optimizer_enabled", True):
			cost_metrics = self._get_cost_optimizer().estimate(base_tokens, tool_trace=tool_trace)

		quality_metric_payload = {
			"metric_date": frappe.utils.nowdate(),
			"model": self.model,
			"messages": 1,
			"quality_score": quality_scores.get("quality_score", 0.0),
			"relevance_score": quality_scores.get("relevance_score", 0.0),
			"completeness_score": quality_scores.get("completeness_score", 0.0),
			"grounding_score": quality_scores.get("grounding_score", 0.0),
			"estimated_cost_usd": cost_metrics.get("estimated_cost_usd", 0.0),
			"prompt_tokens": base_tokens.get("prompt_tokens", 0),
			"completion_tokens": base_tokens.get("completion_tokens", 0),
			"chat": self.chat,
			"message": self.name,
		}
		collector_result = self._get_metrics_collector().persist_quality_metric(quality_metric_payload)

		runtime_audit["monitoring"] = {
			"quality_scores": quality_scores,
			"cost_metrics": cost_metrics,
			"quality_metric_persist": collector_result,
		}

		if experiment_assignment.get("experiment"):
			experiment_metric_result = self._get_metrics_collector().persist_experiment_metric(
				{
					"metric_date": frappe.utils.nowdate(),
					"experiment": experiment_assignment.get("experiment"),
					"variant": experiment_assignment.get("variant"),
					"quality_score": quality_scores.get("quality_score", 0.0),
					"estimated_cost_usd": cost_metrics.get("estimated_cost_usd", 0.0),
					"response_time_ms": round(total_duration_seconds * 1000.0, 2),
					"chat": self.chat,
					"chat_message": self.name,
				}
			)
			runtime_audit["monitoring"]["experiment_metric_persist"] = experiment_metric_result

		if compliance_monitoring_config.get("alerting_enabled", True):
			alert_result = self._get_alerting_system().evaluate_and_create(
				quality_metric_payload,
				config=compliance_monitoring_config,
			)
			runtime_audit["monitoring"]["alerts"] = alert_result

		self._get_realtime_metrics().publish(
			self,
			payload={
				"quality_score": quality_scores.get("quality_score", 0.0),
				"estimated_cost_usd": cost_metrics.get("estimated_cost_usd", 0.0),
				"experiment": experiment_assignment,
			},
		)

		self.runtime_audit = runtime_audit
		self.db_update()
		frappe.db.commit()

		if compliance_monitoring_config.get("audit_logging_enabled", True):
			self._get_audit_logger().log(
				event_name="chat_send_completed",
				status="success",
				details={
					"quality_score": quality_scores.get("quality_score", 0.0),
					"estimated_cost_usd": cost_metrics.get("estimated_cost_usd", 0.0),
				},
				chat=self.chat,
				message=self.name,
			)
		return

	# Sentinel used to detect deepseek-reasoner DSML fallback markup in content.
	_DSML_SEP = "\uff5c"  # ｜ U+FF5C FULLWIDTH VERTICAL LINE

	def _content_looks_like_dsml(self, content):
		"""Return True if content contains deepseek-reasoner DSML function-call markup."""
		sep = self._DSML_SEP
		return bool(content) and f"<{sep}DSML{sep}" in content

	def _build_assistant_message_dict(self, content, reasoning_content, tool_calls):
		message = {
			"role": "assistant",
			"content": content or "",
		}
		if reasoning_content:
			message["reasoning_content"] = reasoning_content
		if tool_calls:
			message["tool_calls"] = tool_calls
		return message

	def _create_non_stream_completion_with_retry(self, client, messages, settings, tools):
		params = {
			"model": self.model,
			"messages": messages,
			"stream": False,
			"max_tokens": self._get_max_completion_tokens(settings, self._extract_latest_user_message(messages)),
		}
		# Only include tools when actually provided — omitting the key entirely
		# ensures the model does not attempt function calling on the final pass.
		if tools:
			params["tools"] = tools

		params.update(self._build_optional_completion_params(settings))
		thinking_config = self._get_thinking_config(settings)
		if thinking_config:
			params["extra_body"] = thinking_config

		max_retries = self._get_max_api_retries(settings)
		retry_backoff_base_seconds = self._get_retry_backoff_base_seconds(settings)
		for attempt in range(1, max_retries + 1):
			try:
				return client.chat.completions.create(**params)
			except Exception as exc:
				if self._strip_unsupported_request_params(params, exc):
					continue
				if attempt >= max_retries or not self._is_retryable_error(exc):
					raise
				time.sleep(retry_backoff_base_seconds * (2 ** (attempt - 1)))

		raise RuntimeError("Failed to create non-stream chat completion")

	def _accumulate_usage(self, aggregate_usage, usage_obj):
		if not usage_obj:
			return
		for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
			try:
				aggregate_usage[key] += int(getattr(usage_obj, key, 0) or 0)
			except Exception:
				continue

	def _get_max_tool_rounds(self, settings):
		return max(1, self._read_int_setting(settings, "max_tool_rounds", DEFAULT_MAX_TOOL_ROUNDS))

	def _get_max_tool_calls_per_round(self, settings):
		return max(1, self._read_int_setting(settings, "max_tool_calls_per_round", DEFAULT_MAX_TOOL_CALLS_PER_ROUND))

	def _get_tool_result_max_chars(self, settings):
		return max(500, self._read_int_setting(settings, "tool_result_max_chars", DEFAULT_TOOL_RESULT_MAX_CHARS))

	def _get_tool_definitions(self, settings=None):
		base_tools = [
			{
				"type": "function",
				"function": {
					"name": "get_security_snapshot",
					"description": "Get market and recommendation snapshot for one security.",
					"parameters": {
						"type": "object",
						"properties": {
							"identifier": {
								"anyOf": [
									{"type": "string", "pattern": "^[A-Za-z0-9._\\-:]{1,64}$"},
									{"type": "string", "format": "uuid"}
								],
								"description": "Security symbol, name, ISIN, or security ID"
							},
							"include_news": {"type": "boolean", "description": "Include latest parsed news items"},
							"news_limit": {
								"anyOf": [
									{"type": "integer", "minimum": 1, "maximum": 10},
									{"type": "string", "pattern": "^[0-9]{1,2}$"}
								],
								"description": "Max news items to include"
							},
							"identifier_type": {
								"type": "string",
								"enum": ["auto", "symbol", "name", "isin", "id"],
								"description": "Optional identifier hint"
							},
						},
						"required": ["identifier"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "get_portfolio_holdings",
					"description": "Get holdings summary for a portfolio.",
					"parameters": {
						"type": "object",
						"properties": {
							"portfolio": {
								"anyOf": [
									{"type": "string", "pattern": "^[A-Za-z0-9._\\- ]{1,140}$"},
									{"type": "string", "format": "uuid"}
								],
								"description": "Portfolio name or ID"
							},
							"limit": {
								"anyOf": [
									{"type": "integer", "minimum": 1, "maximum": 100},
									{"type": "string", "pattern": "^[0-9]{1,3}$"}
								],
								"description": "Max holdings to return"
							},
						},
						"required": ["portfolio"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "get_latest_security_news",
					"description": "Get latest news items for a security.",
					"parameters": {
						"type": "object",
						"properties": {
							"identifier": {
								"anyOf": [
									{"type": "string", "pattern": "^[A-Za-z0-9._\\-:]{1,64}$"},
									{"type": "string", "format": "uuid"}
								],
								"description": "Security symbol, name, ISIN, or security ID"
							},
							"limit": {
								"anyOf": [
									{"type": "integer", "minimum": 1, "maximum": 20},
									{"type": "string", "pattern": "^[0-9]{1,2}$"}
								],
								"description": "Max number of items"
							},
						},
						"required": ["identifier"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "web_search",
					"description": (
						"Search the web and return top textual snippets. "
						"Supports multi-provider search (DuckDuckGo, Wikipedia, SerpAPI) with optional "
						"domain restriction and date-range filtering."
					),
					"parameters": {
						"type": "object",
						"properties": {
							"query": {"type": "string", "minLength": 2, "maxLength": 200, "description": "Search query"},
							"max_results": {
								"anyOf": [
									{"type": "integer", "minimum": 1, "maximum": 10},
									{"type": "string", "pattern": "^[0-9]{1,2}$"}
								],
								"description": "Max results to return",
							},
							"provider": {
								"type": "string",
								"enum": ["auto", "ddgs", "wikipedia", "serpapi"],
								"description": (
									"Search provider: auto selects based on query type, "
									"ddgs uses DuckDuckGo, wikipedia searches Wikipedia, serpapi uses SerpAPI"
								),
							},
							"date_range": {
								"type": "string",
								"enum": ["any", "day", "week", "month", "year"],
								"description": "Filter results by recency: day=last 24 h, week=last 7 d, month=last 30 d, year=last 12 mo",
							},
							"domain_filter": {
								"type": "string",
								"maxLength": 200,
								"description": "Comma-separated domains to restrict search to, e.g. sec.gov,reuters.com,ft.com",
							},
							"result_type": {
								"type": "string",
								"enum": ["snippets", "full"],
								"description": (
									"snippets returns search-result summaries; "
									"full additionally fetches the top result's full page content"
								),
							},
						},
						"required": ["query"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "search_financial",
					"description": (
						"Search financial data sources: SEC EDGAR filings, Yahoo Finance, and "
						"financial news (Reuters, Bloomberg, WSJ, FT, MarketWatch). "
						"Use for company-specific SEC filings (10-K, 10-Q, 8-K), earnings data, "
						"analyst ratings, and financial news. Prefer this over web_search for "
						"equity research and SEC filing retrieval."
					),
					"parameters": {
						"type": "object",
						"properties": {
							"query": {"type": "string", "minLength": 2, "maxLength": 200, "description": "Search query, e.g. company name or financial topic"},
							"ticker": {
								"type": "string",
								"maxLength": 20,
								"description": "Optional stock ticker symbol to narrow results (e.g. AAPL, MSFT)",
							},
							"source": {
								"type": "string",
								"enum": ["auto", "sec_edgar", "yahoo_finance", "financial_news", "serpapi"],
								"description": (
									"Data source: auto aggregates all sources, "
									"sec_edgar searches SEC EDGAR full-text search, "
									"yahoo_finance searches Yahoo Finance, "
									"financial_news restricts to financial news outlets, "
									"serpapi uses SerpAPI web results"
								),
							},
							"form_type": {
								"type": "string",
								"maxLength": 10,
								"description": "SEC form type filter, e.g. 10-K, 10-Q, 8-K (used when source includes sec_edgar)",
							},
							"max_results": {
								"anyOf": [
									{"type": "integer", "minimum": 1, "maximum": 10},
									{"type": "string", "pattern": "^[0-9]{1,2}$"}
								],
								"description": "Max results to return",
							},
						},
						"required": ["query"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "fetch_url_content",
					"description": "Fetch and extract textual content from a URL.",
					"parameters": {
						"type": "object",
						"properties": {
							"url": {
								"type": "string",
								"format": "uri",
								"pattern": "^https?://",
								"description": "HTTP or HTTPS URL"
							},
							"max_chars": {
								"anyOf": [
									{"type": "integer", "minimum": 200, "maximum": 20000},
									{"type": "string", "pattern": "^[0-9]{3,5}$"}
								],
								"description": "Maximum characters in returned content"
							},
						},
						"required": ["url"],
					},
				},
			},
		]

		if settings is not None:
			settings_manager = self._get_settings_manager(settings)
			if not settings_manager.get_tool_execution_config().get("dynamic_registration_enabled", True):
				return base_tools

		return self._get_tool_registry().merge_tool_definitions(base_tools)

	def _execute_tool_call(self, function_name, arguments_raw, chat, portfolio, security, dynamic_registration_enabled=True):
		args = self._safe_json_loads(arguments_raw, default={})
		if not isinstance(args, dict):
			args = {}
		args_key = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
		tool_result_cache = self._get_tool_result_cache()
		chat_name = getattr(chat, "name", None) if chat else None
		portfolio_name = getattr(portfolio, "name", None) if portfolio else None
		security_name = getattr(security, "name", None) if security else None

		cached_result = tool_result_cache.get(
			function_name=function_name,
			args_key=args_key,
			chat_name=chat_name,
			portfolio_name=portfolio_name,
			security_name=security_name,
			dynamic_registration_enabled=bool(dynamic_registration_enabled),
		)
		if cached_result is not None:
			return cached_result

		try:
			result = self._execute_tool_call_cached(
				function_name=function_name,
				args_key=args_key,
				chat_name=chat_name,
				portfolio_name=portfolio_name,
				security_name=security_name,
				dynamic_registration_enabled=bool(dynamic_registration_enabled),
			)
			tool_result_cache.set(
				function_name=function_name,
				args_key=args_key,
				chat_name=chat_name,
				portfolio_name=portfolio_name,
				security_name=security_name,
				dynamic_registration_enabled=bool(dynamic_registration_enabled),
				result=result,
			)
			return result
		except Exception as exc:
			frappe.log_error(title=f"Tool call failed: {function_name}", message=str(exc))
			return {
				"ok": False,
				"args": args,
				"error_code": "tool_execution_error",
				"error": str(exc),
			}

	@lru_cache(maxsize=256)
	def _execute_tool_call_cached(self, function_name, args_key, chat_name, portfolio_name, security_name, dynamic_registration_enabled=True):
		args = self._safe_json_loads(args_key, default={})
		if not isinstance(args, dict):
			args = {}

		portfolio_doc = frappe.get_doc("CF Portfolio", portfolio_name) if portfolio_name else None
		security_doc = frappe.get_doc("CF Security", security_name) if security_name else None

		handlers = {
			"get_security_snapshot": lambda: self._tool_get_security_snapshot(args, security_doc),
			"get_portfolio_holdings": lambda: self._tool_get_portfolio_holdings(args, portfolio_doc),
			"get_latest_security_news": lambda: self._tool_get_latest_security_news(args, security_doc),
			"web_search": lambda: self._tool_web_search(args),
			"search_financial": lambda: self._tool_search_financial(args),
			"fetch_url_content": lambda: self._tool_fetch_url_content(args),
		}

		if dynamic_registration_enabled:
			dynamic_handlers = self._get_tool_registry().get_dynamic_handlers()
			for tool_name, handler in (dynamic_handlers or {}).items():
				handlers[tool_name] = lambda h=handler: self._invoke_dynamic_tool_handler(h, args, portfolio_doc, security_doc)

		if function_name not in handlers:
			return {
				"ok": False,
				"args": args,
				"error_code": "unknown_tool",
				"error": f"Unknown tool '{function_name}'. Available tools: {', '.join(sorted(handlers.keys()))}",
			}

		try:
			result = handlers[function_name]()
			return {"ok": True, "args": args, "result": result}
		except ValueError as exc:
			return {
				"ok": False,
				"args": args,
				"error_code": "validation_error",
				"error": f"Tool '{function_name}' validation failed: {str(exc)}",
			}
		except Exception as exc:
			frappe.log_error(title=f"Tool call failed: {function_name}", message=str(exc))
			return {
				"ok": False,
				"args": args,
				"error_code": "tool_runtime_error",
				"error": f"Tool '{function_name}' execution failed: {str(exc)}",
			}

	def _invoke_dynamic_tool_handler(self, handler, args, portfolio_doc, security_doc):
		try:
			return handler(self, args, portfolio_doc, security_doc)
		except TypeError:
			try:
				return handler(args, portfolio_doc, security_doc)
			except TypeError:
				return handler(args)

	def _tool_get_security_snapshot(self, args, default_security):
		security_doc = self._resolve_security_doc(args.get("identifier"), default_security)
		news_limit = max(1, min(int(args.get("news_limit", 3) or 3), 10))
		include_news = bool(args.get("include_news", False))

		payload = {
			"security": security_doc.name,
			"security_name": security_doc.security_name,
			"symbol": security_doc.symbol,
			"security_type": security_doc.security_type,
			"currency": security_doc.currency,
			"current_price": security_doc.current_price,
			"suggestion_action": security_doc.suggestion_action,
			"suggestion_rating": security_doc.suggestion_rating,
			"suggestion_buy_price": security_doc.suggestion_buy_price,
			"suggestion_sell_price": security_doc.suggestion_sell_price,
			"suggestion_fair_value": security_doc.suggestion_fair_value,
		}

		if include_news:
			payload["news"] = self._extract_security_news_items(security_doc, news_limit)

		return payload

	def _tool_get_latest_security_news(self, args, default_security):
		security_doc = self._resolve_security_doc(args.get("identifier"), default_security)
		limit = max(1, min(int(args.get("limit", 5) or 5), 20))
		return {
			"security": security_doc.name,
			"symbol": security_doc.symbol,
			"items": self._extract_security_news_items(security_doc, limit),
		}

	def _tool_get_portfolio_holdings(self, args, default_portfolio):
		portfolio_doc = self._resolve_portfolio_doc(args.get("portfolio"), default_portfolio)
		limit = max(1, min(int(args.get("limit", 20) or 20), 100))

		holdings = frappe.get_all(
			"CF Portfolio Holding",
			filters={"portfolio": portfolio_doc.name},
			fields=[
				"security",
				"security_name",
				"quantity",
				"current_value",
				"allocation_percentage",
				"profit_loss",
				"profit_loss_percentage",
				"current_price",
				"average_purchase_price",
				"suggestion_action",
			],
			order_by="allocation_percentage desc",
			limit_page_length=limit,
		)

		return {
			"portfolio": portfolio_doc.name,
			"portfolio_name": portfolio_doc.portfolio_name,
			"currency": portfolio_doc.currency,
			"current_value": portfolio_doc.current_value,
			"cost": portfolio_doc.cost,
			"risk_profile": portfolio_doc.risk_profile,
			"holdings": holdings,
		}

	def _tool_fetch_url_content(self, args):
		url = (args.get("url") or "").strip()
		if not (url.startswith("http://") or url.startswith("https://")):
			raise ValueError("url must start with http:// or https://")

		max_chars = max(200, min(int(args.get("max_chars", DEFAULT_TOOL_RESULT_MAX_CHARS) or DEFAULT_TOOL_RESULT_MAX_CHARS), 20000))
		content_cache = self._get_content_summarization_cache()
		extracted = content_cache.get(url=url, max_chars=max_chars)
		if extracted is None:
			extracted = fetch_and_embed_url_content(url, self)
			content_cache.set(url=url, max_chars=max_chars, content=extracted)
		if extracted and len(extracted) > max_chars:
			extracted = extracted[:max_chars] + "..."

		return {
			"url": url,
			"content": extracted,
		}

	def _tool_web_search(self, args):
		query = (args.get("query") or "").strip()
		if not query:
			raise ValueError("query is required")

		max_results = max(1, min(int(args.get("max_results", 5) or 5), 10))
		provider = (args.get("provider") or "auto").strip().lower()
		date_range = (args.get("date_range") or "any").strip().lower()
		domain_filter = (args.get("domain_filter") or "").strip()
		result_type = (args.get("result_type") or "snippets").strip().lower()

		providers = None
		if provider in ("ddgs", "wikipedia"):
			providers = [provider]

		results = self._get_web_search_service().search_web_results(
			query,
			num_results=max_results,
			providers=providers,
			domain_filter=domain_filter or None,
			result_type=result_type,
			date_range=None if date_range in ("", "any") else date_range,
		)
		return {
			"query": query,
			"count": len(results),
			"providers_used": sorted({r.get("source", "unknown") for r in results}),
			"results": results,
		}

	def _tool_search_financial(self, args):
		query = (args.get("query") or "").strip()
		if not query:
			raise ValueError("query is required")

		ticker = (args.get("ticker") or "").strip() or None
		source = (args.get("source") or "auto").strip().lower()
		form_type = (args.get("form_type") or "").strip() or None
		max_results = max(1, min(int(args.get("max_results", 5) or 5), 10))

		results = self._get_web_search_service().search_financial_sources(
			query=query,
			ticker=ticker,
			source=source,
			form_type=form_type,
			max_results=max_results,
		)
		return {
			"query": query,
			"ticker": ticker,
			"source": source,
			"count": len(results),
			"providers_used": sorted({r.get("source", "unknown") for r in results}),
			"results": results,
		}

	def _resolve_security_doc(self, identifier, default_security):
		if default_security and (not identifier or str(identifier).strip() == ""):
			return default_security

		identifier = (identifier or "").strip()
		if not identifier:
			raise ValueError("Security identifier is required")

		exact_name = frappe.db.exists("CF Security", identifier)
		if exact_name:
			return frappe.get_doc("CF Security", exact_name)

		matches = frappe.get_all(
			"CF Security",
			filters={"isin": identifier},
			fields=["name"],
			limit_page_length=1,
		)
		if matches:
			return frappe.get_doc("CF Security", matches[0].name)

		matches = frappe.get_all(
			"CF Security",
			filters={"security_name": identifier},
			fields=["name"],
			limit_page_length=1,
		)
		if matches:
			return frappe.get_doc("CF Security", matches[0].name)

		raise ValueError(f"Security not found: {identifier}")

	def _resolve_portfolio_doc(self, portfolio_name, default_portfolio):
		if default_portfolio and (not portfolio_name or str(portfolio_name).strip() == ""):
			return default_portfolio

		portfolio_name = (portfolio_name or "").strip()
		if not portfolio_name:
			raise ValueError("Portfolio is required")

		exact = frappe.db.exists("CF Portfolio", portfolio_name)
		if exact:
			return frappe.get_doc("CF Portfolio", exact)

		matches = frappe.get_all(
			"CF Portfolio",
			filters={"portfolio_name": portfolio_name},
			fields=["name"],
			limit_page_length=1,
		)
		if matches:
			return frappe.get_doc("CF Portfolio", matches[0].name)

		raise ValueError(f"Portfolio not found: {portfolio_name}")

	def _extract_security_news_items(self, security_doc, limit):
		news_data = self._safe_json_loads(getattr(security_doc, "news", None), default=[])
		if not isinstance(news_data, list):
			return []

		items = []
		for item in news_data[:limit]:
			if not isinstance(item, dict):
				continue
			content = item.get("content") or {}
			if not isinstance(content, dict):
				content = {}
			items.append({
				"title": content.get("title") or item.get("title"),
				"summary": content.get("summary") or item.get("summary"),
				"url": content.get("canonicalUrl", {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else item.get("link"),
				"provider": content.get("provider", {}).get("displayName") if isinstance(content.get("provider"), dict) else item.get("publisher"),
				"published_at": content.get("pubDate") or item.get("providerPublishTime"),
			})
		return items

	def _safe_json_loads(self, value, default):
		if value in (None, ""):
			return default
		if isinstance(value, (dict, list)):
			return value
		try:
			return json.loads(value)
		except Exception:
			return default

	def _is_reasoner_model(self, model_name, settings=None):
		normalized_model = (model_name or "").strip().lower()
		return normalized_model.startswith("deepseek-reasoner")

	def _is_deepseek_chat_model(self, model_name):
		normalized_model = (model_name or "").strip().lower()
		return normalized_model.startswith("deepseek-chat")

	def _get_max_completion_tokens(self, settings, prompt_text=None):
		if self._is_reasoner_model(self.model, settings):
			default_tokens = self._read_int_setting(settings, "reasoner_default_max_tokens", DEFAULT_REASONER_MAX_TOKENS)
			max_cap = self._read_int_setting(settings, "reasoner_max_tokens_cap", MAX_REASONER_MAX_TOKENS)
			if self._get_token_manager().is_complex_query(prompt_text):
				adaptive_tokens = int(default_tokens * 1.25)
				default_tokens = max(default_tokens, adaptive_tokens)
			return max(1, min(default_tokens, max_cap))

		default_tokens = self._read_int_setting(settings, "chat_default_max_tokens", DEFAULT_CHAT_MAX_TOKENS)
		max_cap = self._read_int_setting(settings, "chat_max_tokens_cap", MAX_CHAT_MAX_TOKENS)
		if self._is_deepseek_chat_model(self.model):
			# DeepSeek chat endpoints reject maxtokens above 8192.
			max_cap = min(max_cap, DEEPSEEK_CHAT_MAX_TOKENS_CAP)
		return max(1, min(default_tokens, max_cap))

	def _get_max_context_tokens(self, settings):
		return max(1, self._read_int_setting(settings, "max_context_tokens", MAX_CONTEXT_TOKENS))

	def _get_max_api_retries(self, settings):
		return max(1, self._read_int_setting(settings, "max_api_retries", MAX_OPENAI_RETRIES))

	def _get_retry_backoff_base_seconds(self, settings):
		return max(0.1, self._read_float_setting(settings, "retry_backoff_base_seconds", RETRY_BACKOFF_BASE_SECONDS))

	def _thinking_enabled_for_chat_models(self, settings):
		manager = self._get_settings_manager(settings)
		return manager.get_feature_flag("thinking_enabled", default=False)

	def _is_thinking_mode_active(self, settings):
		if self._is_reasoner_model(self.model, settings):
			return True

		return self._is_deepseek_chat_model(self.model) and self._thinking_enabled_for_chat_models(settings)

	def _get_thinking_type(self, settings):
		value = (settings.get("thinking_type") or DEFAULT_THINKING_TYPE).strip().lower()
		if not value:
			return DEFAULT_THINKING_TYPE
		return value

	def _get_thinking_budget_tokens(self, settings):
		return max(128, self._read_int_setting(settings, "thinking_budget_tokens", DEFAULT_THINKING_BUDGET_TOKENS))

	def _get_thinking_config(self, settings):
		if not self._is_thinking_mode_active(settings):
			return None

		return {
			"thinking": {
				"type": self._get_thinking_type(settings),
				"budget_tokens": self._get_thinking_budget_tokens(settings),
			}
		}

	def _json_mode_enabled(self, settings):
		manager = self._get_settings_manager(settings)
		return manager.get_feature_flag("json_mode_enabled", default=False)

	def _get_seed_value(self, settings):
		seed_raw = settings.get("seed_value")
		if seed_raw in (None, ""):
			return None
		try:
			seed_value = int(seed_raw)
		except (TypeError, ValueError):
			return None
		return seed_value if seed_value >= 0 else None

	def _get_top_p(self, settings):
		value = self._read_signed_float_setting(settings, "top_p", DEFAULT_TOP_P)
		if value < 0:
			return 0.0
		if value > 1:
			return 1.0
		return value

	def _get_frequency_penalty(self, settings):
		value = self._read_signed_float_setting(settings, "frequency_penalty", DEFAULT_FREQUENCY_PENALTY)
		return max(-2.0, min(2.0, value))

	def _get_presence_penalty(self, settings):
		value = self._read_signed_float_setting(settings, "presence_penalty", DEFAULT_PRESENCE_PENALTY)
		return max(-2.0, min(2.0, value))

	def _build_optional_completion_params(self, settings):
		params = {}

		if self._json_mode_enabled(settings):
			params["response_format"] = {"type": "json_object"}

		if self._is_thinking_mode_active(settings):
			return params

		params["temperature"] = 1.0
		params["top_p"] = self._get_top_p(settings)
		params["frequency_penalty"] = self._get_frequency_penalty(settings)
		params["presence_penalty"] = self._get_presence_penalty(settings)

		seed = self._get_seed_value(settings)
		if seed is not None:
			params["seed"] = seed

		return params

	def _strip_unsupported_request_params(self, params, exc):
		error_text = str(exc).lower()
		removed = False

		if "response_format" in error_text and "response_format" in params:
			params.pop("response_format", None)
			removed = True

		if "seed" in error_text and "seed" in params:
			params.pop("seed", None)
			removed = True

		if any(keyword in error_text for keyword in ("top_p", "frequency_penalty", "presence_penalty", "temperature")):
			for key in ("top_p", "frequency_penalty", "presence_penalty", "temperature"):
				if key in params:
					params.pop(key, None)
					removed = True

		if any(keyword in error_text for keyword in ("extra_body", "thinking")) and "extra_body" in params:
			params.pop("extra_body", None)
			removed = True

		if removed:
			frappe.logger("cognitive_folio").warning(
				"Removed unsupported completion params for %s after API error: %s",
				self.name,
				error_text,
			)

		return removed

	def _extract_latest_user_message(self, messages):
		for message in reversed(messages or []):
			if isinstance(message, dict) and message.get("role") == "user":
				return message.get("content") or ""
		return ""

	def _conversation_summarization_enabled(self, settings):
		manager = self._get_settings_manager(settings)
		return manager.get_feature_flag("enable_conversation_summarization", default=False)

	def _read_int_setting(self, settings, fieldname, default_value):
		manager = self._get_settings_manager(settings)
		return manager.get_int(fieldname, default_value, minimum=1)

	def _read_float_setting(self, settings, fieldname, default_value):
		manager = self._get_settings_manager(settings)
		return manager.get_float(fieldname, default_value, minimum=0.000001)

	def _read_signed_float_setting(self, settings, fieldname, default_value):
		manager = self._get_settings_manager(settings)
		return manager.get_float(fieldname, default_value)

	def _is_retryable_error(self, exc):
		status_code = getattr(exc, "status_code", None)
		if status_code in {408, 409, 429}:
			return True
		if isinstance(status_code, int) and status_code >= 500:
			return True

		exception_name = exc.__class__.__name__.lower()
		if any(keyword in exception_name for keyword in ("timeout", "ratelimit", "connection", "apierror", "apitimeouterror")):
			return True

		error_text = str(exc).lower()
		return any(keyword in error_text for keyword in ("timed out", "timeout", "rate limit", "temporarily unavailable", "connection reset"))

	def prepare_prompt(self, portfolio, security):
		"""Prepare the prompt with variable replacements"""
		prompt = self.prompt
		
		# Replace ((variable)) with portfolio fields
		if portfolio:
			prompt = re.sub(r'\(\((\w+)\)\)', lambda match: replace_variables(match, portfolio), prompt)
			
			# Handle holdings processing (existing code)
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters={"portfolio": portfolio.name},
				fields=["name", "security"]
			)
			
			if holdings:
				holdings_pattern = r'\*\*\*HOLDINGS\*\*\*(.*?)\*\*\*HOLDINGS\*\*\*'
				holdings_matches = re.findall(holdings_pattern, prompt, re.DOTALL)
				
				if holdings_matches:
					all_holding_sections = []
					
					for holding_info in holdings:
						holding_doc = frappe.get_doc("CF Portfolio Holding", holding_info.name)
						security_doc = frappe.get_doc("CF Security", holding_info.security)
						
						holding_sections = []
						for holdings_content in holdings_matches:
							holding_prompt = holdings_content
							
							holding_prompt = re.sub(r'\{\{([\w\.]+)\}\}', lambda match: replace_variables(match, security_doc), holding_prompt)
							holding_prompt = re.sub(r'\[\[([\w\.]+)\]\]', lambda match: replace_variables(match, holding_doc), holding_prompt)
							
							holding_sections.append(holding_prompt)
						
						all_holding_sections.append("***HOLDINGS***" + "***HOLDINGS******HOLDINGS***".join(holding_sections) + "***HOLDINGS***")
					
					parts = re.split(r'\*\*\*HOLDINGS\*\*\*.*?\*\*\*HOLDINGS\*\*\*', prompt, flags=re.DOTALL)
					
					final_parts = []
					final_parts.append(parts[0])
					
					for holding_section in all_holding_sections:
						clean_holding_section = holding_section.replace("***HOLDINGS***", "")
						final_parts.append(clean_holding_section)
					
					if len(parts) > 1:
						final_parts.append(parts[-1])
					
					prompt = "\n\n".join(final_parts)
		
		elif security:
			# Expand financials placeholder with period parameters (edgar cache first, yfinance fallback)
			financials_pattern = r'\{\{financials:y(\d+):q(\d+)\}\}'

			def _replace_financials(match):
				years = int(match.group(1))
				quarters = int(match.group(2))
				try:
					return expand_financials_variable(security, years, quarters)
				except Exception as e:
					frappe.log_error(f"Financials expansion failed for {security.name if hasattr(security, 'name') else 'unknown'}: {str(e)}")
					return "[financial data unavailable]"

			prompt = re.sub(financials_pattern, _replace_financials, prompt)
			
			# Expand edgar text sections placeholder
			# Pattern: {{edgar:form:year_or_index[:param1][:param2]}}
			# param1 and param2 can be section keywords (risk/mda/business/legal/all) or quarters (Q1/Q2/Q3)
			# Examples: {{edgar:10-K:-1}}, {{edgar:10-K:-1:risk}}, {{edgar:10-Q:2024:Q2}}, {{edgar:10-Q:2024:Q2:mda}}, {{edgar:8-K:2024}}
			edgar_pattern = r'\{\{edgar:([^:]+):([^:]+)(?::([^:}]+))?(?::([^}]+))?\}\}'
			
			def _replace_edgar(match):
				form_type = match.group(1).strip()
				year_or_index = match.group(2).strip()
				param1 = match.group(3).strip() if match.group(3) else None
				param2 = match.group(4).strip() if match.group(4) else None
				
				# Intelligently determine which params are section vs quarter
				section = None
				quarter = None
				
				# Check if params are quarters (Q1, Q2, Q3) or sections (risk, mda, business, legal, all)
				section_keywords = ['risk', 'mda', 'business', 'legal', 'all']
				quarter_keywords = ['Q1', 'Q2', 'Q3']
				
				if param1:
					if param1 in quarter_keywords:
						quarter = param1
					elif param1 in section_keywords:
						section = param1
					else:
						# Default: treat as section for 10-K/8-K, quarter for 10-Q
						if form_type == '10-Q' and param1.upper() in quarter_keywords:
							quarter = param1.upper()
						else:
							section = param1
				
				if param2:
					if param2 in quarter_keywords:
						quarter = param2
					elif param2 in section_keywords:
						section = param2
					else:
						# If param1 was quarter, param2 is section; otherwise param2 is quarter
						if quarter:
							section = param2
						else:
							quarter = param2.upper() if param2.upper() in quarter_keywords else param2
				
				try:
					return expand_edgar_section_variable(security, form_type, year_or_index, section, quarter)
				except Exception as e:
					frappe.log_error(f"Edgar variable expansion failed for {security.name if hasattr(security, 'name') else 'unknown'}: {str(e)}")
					return f"[SEC filing not available: {form_type} {year_or_index}]"
			
			prompt = re.sub(edgar_pattern, _replace_edgar, prompt)
			
			# Expand regular security field variables
			prompt = re.sub(r'\{\{([\w\.]+)\}\}', lambda match: replace_variables(match, security), prompt)
		
		return prompt

	def extract_pdf_text(self):
		"""Extract text and tables from specific PDF files referenced in the prompt.
		
		Uses pdfplumber for better table extraction and converts tables to markdown format.
		"""
		try:
			import pdfplumber
			import os
			import html
		except ImportError:
			frappe.log_error("pdfplumber not installed", "PDF Extraction Error")
			return self.prompt
		
		prompt = self.prompt
		
		# First, decode any HTML entities
		prompt = html.unescape(prompt)
		
		# Find all PDF file references in both formats:
		# <<filename.pdf>> and &lt;&lt;filename.pdf&gt;&gt;
		pdf_references = []
		
		# Pattern for normal angle brackets
		normal_pattern = r'<<([^>]+\.pdf)>>'
		pdf_references.extend(re.findall(normal_pattern, prompt, re.IGNORECASE))
		
		# Pattern for HTML encoded angle brackets
		encoded_pattern = r'&lt;&lt;([^&]+\.pdf)&gt;&gt;'
		pdf_references.extend(re.findall(encoded_pattern, prompt, re.IGNORECASE))
		
		if not pdf_references:
			return prompt
		
		# Get all file attachments for current chat message
		files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "CF Chat Message",
				"attached_to_name": self.name,
				"file_url": ["like", "%.pdf"]
			},
			fields=["file_url", "file_name"]
		)
		
		# Create a mapping of file names to file info
		file_mapping = {}
		for file_info in files:
			file_mapping[file_info.file_name.lower()] = file_info
		
		# Replace each PDF reference with its content
		for pdf_filename in pdf_references:
			pdf_key = pdf_filename.lower()
			
			if pdf_key in file_mapping:
				file_info = file_mapping[pdf_key]
				try:
					# Get the full file path
					file_path = frappe.get_site_path() + file_info.file_url
                    
					if os.path.exists(file_path):
						# Extract text and tables from PDF using pdfplumber
						markdown_content = self._extract_pdf_with_tables(file_path)
							
						if markdown_content.strip():
							# Replace the reference with the file content
							replacement = f"--- Content of {file_info.file_name} ---\n{markdown_content.strip()}\n--- End of {file_info.file_name} ---"
							
							# Replace both normal and encoded versions
							prompt = prompt.replace(f"<<{pdf_filename}>>", replacement)
							prompt = prompt.replace(f"&lt;&lt;{pdf_filename}&gt;&gt;", replacement)
						else:
							# Replace with message indicating no text found
							no_text_msg = f"[No readable text found in {file_info.file_name}]"
							prompt = prompt.replace(f"<<{pdf_filename}>>", no_text_msg)
							prompt = prompt.replace(f"&lt;&lt;{pdf_filename}&gt;&gt;", no_text_msg)
				
				except Exception as e:
					frappe.log_error(f"Error extracting PDF text from {file_info.file_name}: {str(e)}")
					# Replace with error message
					error_msg = f"[Error reading {file_info.file_name}]"
					prompt = prompt.replace(f"<<{pdf_filename}>>", error_msg)
					prompt = prompt.replace(f"&lt;&lt;{pdf_filename}&gt;&gt;", error_msg)
			else:
				# File not found, replace with message
				not_found_msg = f"[File {pdf_filename} not found in attachments]"
				prompt = prompt.replace(f"<<{pdf_filename}>>", not_found_msg)
				prompt = prompt.replace(f"&lt;&lt;{pdf_filename}&gt;&gt;", not_found_msg)
		
		return prompt

	def _extract_pdf_with_tables(self, file_path: str) -> str:
		"""Extract text and tables from PDF, converting tables to markdown.
		
		Args:
			file_path: Path to the PDF file
			
		Returns:
			Markdown-formatted content with tables
		"""
		import pdfplumber
		
		content_parts = []
		
		with pdfplumber.open(file_path) as pdf:
			for page_num, page in enumerate(pdf.pages, start=1):
				page_content = []
				
				# Extract tables from the page
				tables = page.extract_tables()
				
				if tables:
					# If page has tables, extract them as markdown
					for table_idx, table in enumerate(tables, start=1):
						if table and len(table) > 1:  # Ensure table has headers and data
							markdown_table = self._table_to_markdown(table)
							if markdown_table:
								page_content.append(f"\n{markdown_table}\n")
				
				# Extract regular text (non-table content)
				text = page.extract_text()
				if text:
					# Remove excessive whitespace
					text = re.sub(r'\n{3,}', '\n\n', text)
					page_content.append(text)
				
				# Combine page content
				if page_content:
					page_text = "\n\n".join(page_content)
					content_parts.append(page_text)
		
		return "\n\n".join(content_parts)

	def _table_to_markdown(self, table_data) -> str:
		"""Convert a list of lists (table data) to markdown table format.
		
		Args:
			table_data: List of lists where first row is treated as headers
			
		Returns:
			Markdown formatted table string
		"""
		if not table_data or len(table_data) < 2:
			return ""
		
		# Clean and prepare data
		cleaned_data = []
		for row in table_data:
			cleaned_row = [str(cell).strip() if cell else "" for cell in row]
			cleaned_data.append(cleaned_row)
		
		# Determine column widths
		col_count = max(len(row) for row in cleaned_data)
		
		# Skip tables that are too narrow (likely parsing errors)
		if col_count < 2:
			return ""
		
		# Normalize all rows to have same number of columns
		for row in cleaned_data:
			while len(row) < col_count:
				row.append("")
		
		# Build markdown table
		lines = []
		
		# Header row
		header = cleaned_data[0]
		lines.append("| " + " | ".join(header) + " |")
		
		# Separator row
		lines.append("| " + " | ".join(["---"] * col_count) + " |")
		
		# Data rows
		for row in cleaned_data[1:]:
			lines.append("| " + " | ".join(row) + " |")
		
		return "\n".join(lines)

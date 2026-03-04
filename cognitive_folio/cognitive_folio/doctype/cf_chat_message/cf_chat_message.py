import frappe
from frappe.model.document import Document
import re
import time
import json
from cognitive_folio.utils.markdown import safe_markdown_to_html
from cognitive_folio.utils.helper import replace_variables, expand_financials_variable, expand_edgar_section_variable
from cognitive_folio.utils.url_fetcher import fetch_and_embed_url_content


MAX_CONTEXT_TOKENS = 120000
DEFAULT_CHAT_MAX_TOKENS = 4000
DEFAULT_REASONER_MAX_TOKENS = 32000
MAX_CHAT_MAX_TOKENS = 8000
MAX_REASONER_MAX_TOKENS = 64000
MAX_OPENAI_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 1.5
STREAM_FLUSH_INTERVAL_SECONDS = 1.0
STREAM_FLUSH_MIN_CHAR_DELTA = 120
TOOL_CALLS_ENABLED_DEFAULT = 1
DEFAULT_MAX_TOOL_ROUNDS = 8
DEFAULT_MAX_TOOL_CALLS_PER_ROUND = 8
DEFAULT_TOOL_RESULT_MAX_CHARS = 8000

class CFChatMessage(Document):

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
			
			# Update status to processing
			message_doc.db_set("status", "Processing", update_modified=False)
			frappe.db.commit()
			
			# Process the message (use the reloaded document)
			message_doc.send()
			
			# Update status to success and save the response
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
		client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
		runtime_audit = {
			"model": self.model,
			"augmentations": [],
			"web_search": {
				"enabled": bool(getattr(self, 'web_search', False)),
				"query": None,
				"results_count": 0,
				"fallback": None,
			},
			"tools": {
				"enabled": self._tool_calls_enabled(settings),
				"rounds": 0,
				"calls": 0,
				"names": [],
			},
		}
	
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
		runtime_prompt = self._prepare_prompt_without_mutation(original_prompt, portfolio, security)
		if runtime_prompt != original_prompt:
			runtime_audit["augmentations"].append("template_variables")

		# Detect URLs and embed their content (guarded by optional checkbox)
		if getattr(self, 'fetch_urls', False):
			try:
				before_prompt = runtime_prompt
				runtime_prompt = fetch_and_embed_url_content(runtime_prompt, self)
				if runtime_prompt != before_prompt:
					runtime_audit["augmentations"].append("url_content")
			except Exception as e:
				frappe.log_error(f"URL embedding failed for message {self.name}: {str(e)}", "URL Fetch Error")
		
		# Extract PDF text and tables, convert to markdown if available
		try:
			before_prompt = runtime_prompt
			runtime_prompt = self._extract_pdf_text_for_prompt(runtime_prompt)
			if runtime_prompt != before_prompt:
				runtime_audit["augmentations"].append("pdf_extraction")
		except Exception as e:
			frappe.log_error(f"PDF extraction failed for message {self.name}: {str(e)}", "PDF Extraction Error")
		
		# NEW: Perform web search if checkbox is enabled
		if getattr(self, 'web_search', False):  # Check if web_search field exists and is True
			try:
				# Use OpenAI to extract intelligent search query
				search_query = self.extract_search_query(runtime_prompt)
				if search_query:
					runtime_audit["web_search"]["query"] = (search_query or "")[:200]
					search_results = self.perform_web_search(search_query)
					if search_results:
						runtime_audit["web_search"]["results_count"] = self._count_markdown_search_results(search_results)
						runtime_audit["web_search"]["fallback"] = "resolved"
						# Prepend search results to the prompt only when useful content exists
						runtime_prompt = f"{search_results}\n\n--- User Query ---\n{runtime_prompt}"
						runtime_audit["augmentations"].append("web_search")
					else:
						runtime_audit["web_search"]["fallback"] = "no_results_all_providers"
			except Exception as e:
				frappe.log_error(f"Web search failed for message {self.name}: {str(e)}", "Web Search Error")
				# Continue without web search if it fails
    
		current_prompt_tokens = len(encoding.encode(runtime_prompt or ""))
		available_tokens -= current_prompt_tokens
		
		# Add previous messages while staying within token limit
		used_tokens = 0
		for message in chat_messages:  # Already ordered in most recent first order
			user_tokens = len(encoding.encode(message.prompt or ""))
			assistant_tokens = len(encoding.encode(message.response or ""))
			message_tokens = user_tokens + assistant_tokens
			
			if used_tokens + message_tokens > available_tokens:
				break  # Stop adding messages if we exceed token limit
				
			# Insert at position 1 to maintain chronological order (after system message)
			messages.insert(1, {"role": "user", "content": message.prompt or ""})
			messages.insert(2, {"role": "assistant", "content": message.response or ""})
			used_tokens += message_tokens
		
		# Add current message
		messages.append({"role": "user", "content": runtime_prompt})

		if self._tool_calls_enabled(settings):
			full_response, reasoning_content, finish_reason, usage_summary, tool_trace = self._run_tool_call_chain(
				client=client,
				messages=messages,
				settings=settings,
				chat=chat,
				portfolio=portfolio,
				security=security,
			)

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
			})

			self.tokens = base_tokens
			self.tokens["prompt_augmented"] = bool(runtime_prompt != original_prompt)
			self.tokens["prompt_original_length"] = len(original_prompt or "")
			self.tokens["prompt_runtime_length"] = len(runtime_prompt or "")
			runtime_audit["tools"]["rounds"] = int((usage_summary or {}).get("tool_rounds", 0) or 0) if isinstance(usage_summary, dict) else 0
			runtime_audit["tools"]["calls"] = len(tool_trace or [])
			runtime_audit["tools"]["names"] = sorted({(item or {}).get("tool") for item in (tool_trace or []) if (item or {}).get("tool")})
			runtime_audit["prompt_augmented"] = bool(runtime_prompt != original_prompt)
			self.runtime_audit = runtime_audit
			self.db_update()
			frappe.db.commit()
			return
	
		response = self._create_streaming_completion_with_retry(client, messages, settings)
	
		# Initialize response variables
		full_response = ""
		reasoning_content = ""
		finish_reason = None
		last_saved_response_length = 0
		last_saved_reasoning_length = 0
		last_flush_at = time.time()
		stream_flush_interval_seconds = self._get_stream_flush_interval_seconds(settings)
		stream_flush_min_char_delta = self._get_stream_flush_min_char_delta(settings)
		
		# Process streaming chunks
		for chunk in response:
			if chunk.choices and len(chunk.choices) > 0:
				choice = chunk.choices[0]
				content_updated = False
				if getattr(choice, "finish_reason", None):
					finish_reason = choice.finish_reason
				
				# Handle reasoning content if available
				if hasattr(choice.delta, 'reasoning_content') and choice.delta.reasoning_content:
					reasoning_content += choice.delta.reasoning_content
					content_updated = True
				
				# Handle message content
				if hasattr(choice.delta, 'content') and choice.delta.content:
					full_response += choice.delta.content
					content_updated = True
				
				# Send update if either content or reasoning was updated
				if content_updated:
					now_ts = time.time()
					response_delta = len(full_response) - last_saved_response_length
					reasoning_delta = len(reasoning_content) - last_saved_reasoning_length
					should_flush = (
						response_delta >= stream_flush_min_char_delta
						or reasoning_delta >= stream_flush_min_char_delta
						or (now_ts - last_flush_at) >= stream_flush_interval_seconds
					)

					if should_flush:
						# Update the document with the current partial response
						self.response = full_response
						self.response_html = safe_markdown_to_html(full_response)
						self.reasoning = reasoning_content

						# Save the partial response to database
						self.db_update()
						frappe.db.commit()

						last_saved_response_length = len(full_response)
						last_saved_reasoning_length = len(reasoning_content)
						last_flush_at = now_ts

						# Notify frontend to reload the frame
						self._publish_chat_realtime(
							event_name='cf_streaming_update',
							payload={
								'message_id': self.name,
								'chat_id': self.chat,
								'message': full_response,
								'reasoning': reasoning_content,
								'status': 'streaming'
							}
						)
					
		# Final update with complete response
		self.response = full_response
		self.response_html = safe_markdown_to_html(full_response)
		self.reasoning = reasoning_content
		
		# Note: tokens might not be available in streaming mode
		# You might need to calculate them manually or handle differently
		total_duration_seconds = round(time.time() - request_started_at, 3)
		try:
			# Some streaming responses might still have usage info
			if hasattr(response, 'usage'):
				self.tokens = response.usage.to_json()
		except:
			# Calculate tokens manually if usage not available
			response_tokens = len(encoding.encode(full_response))
			prompt_tokens = current_prompt_tokens + system_tokens + used_tokens
			total_tokens = prompt_tokens + response_tokens
			
			self.tokens = {
				"prompt_tokens": prompt_tokens,
				"completion_tokens": response_tokens,
				"total_tokens": total_tokens
			}

		if not isinstance(self.tokens, dict):
			if isinstance(self.tokens, str):
				try:
					import json
					self.tokens = json.loads(self.tokens)
				except Exception:
					self.tokens = {"raw_usage": self.tokens}
			else:
				self.tokens = {}

		self.tokens.update({
			"model": self.model,
			"finish_reason": finish_reason,
			"duration_seconds": total_duration_seconds,
			"max_tokens": self._get_max_completion_tokens(settings),
			"tool_calls_enabled": False,
			"prompt_augmented": bool(runtime_prompt != original_prompt),
			"prompt_original_length": len(original_prompt or ""),
			"prompt_runtime_length": len(runtime_prompt or ""),
		})
		runtime_audit["prompt_augmented"] = bool(runtime_prompt != original_prompt)
		self.runtime_audit = runtime_audit

	def _count_markdown_search_results(self, search_results_markdown):
		if not search_results_markdown:
			return 0
		return len(re.findall(r"^\d+\.\s", search_results_markdown, flags=re.MULTILINE))

	def _prepare_prompt_without_mutation(self, prompt_text, portfolio, security):
		original_prompt = self.prompt
		try:
			self.prompt = prompt_text
			return self.prepare_prompt(portfolio, security)
		finally:
			self.prompt = original_prompt

	def _extract_pdf_text_for_prompt(self, prompt_text):
		original_prompt = self.prompt
		try:
			self.prompt = prompt_text
			return self.extract_pdf_text()
		finally:
			self.prompt = original_prompt

	def _run_tool_call_chain(self, client, messages, settings, chat, portfolio, security):
		tools = self._get_tool_definitions()
		max_rounds = self._get_max_tool_rounds(settings)
		max_tool_calls_per_round = self._get_max_tool_calls_per_round(settings)
		tool_result_max_chars = self._get_tool_result_max_chars(settings)

		all_reasoning_parts = []
		tool_trace = []
		last_finish_reason = None
		aggregate_usage = {
			"tool_rounds": 0,
			"prompt_tokens": 0,
			"completion_tokens": 0,
			"total_tokens": 0,
		}

		for round_index in range(1, max_rounds + 1):
			response = self._create_non_stream_completion_with_retry(
				client=client,
				messages=messages,
				settings=settings,
				tools=tools,
			)
			aggregate_usage["tool_rounds"] = round_index
			self._accumulate_usage(aggregate_usage, getattr(response, "usage", None))

			if not response.choices:
				raise RuntimeError("Tool-chain completion returned no choices")

			choice = response.choices[0]
			message = choice.message
			assistant_content = getattr(message, "content", None) or ""
			reasoning_content = getattr(message, "reasoning_content", None) or ""
			if reasoning_content:
				all_reasoning_parts.append(reasoning_content)

			tool_calls = list(getattr(message, "tool_calls", None) or [])
			last_finish_reason = getattr(choice, "finish_reason", None)

			if not tool_calls:
				messages.append(self._build_assistant_message_dict(assistant_content, reasoning_content, []))
				return assistant_content, "\n\n".join(all_reasoning_parts), last_finish_reason, aggregate_usage, tool_trace

			assistant_tool_calls = []
			for tc in tool_calls[:max_tool_calls_per_round]:
				call_id = getattr(tc, "id", None)
				function_obj = getattr(tc, "function", None)
				function_name = getattr(function_obj, "name", "") if function_obj else ""
				arguments_raw = getattr(function_obj, "arguments", "{}") if function_obj else "{}"
				assistant_tool_calls.append({
					"id": call_id,
					"type": "function",
					"function": {
						"name": function_name,
						"arguments": arguments_raw,
					},
				})

			messages.append(self._build_assistant_message_dict(assistant_content, reasoning_content, assistant_tool_calls))

			for tc in tool_calls[:max_tool_calls_per_round]:
				call_started = time.time()
				call_id = getattr(tc, "id", None)
				function_obj = getattr(tc, "function", None)
				function_name = getattr(function_obj, "name", "") if function_obj else ""
				arguments_raw = getattr(function_obj, "arguments", "{}") if function_obj else "{}"

				tool_result = self._execute_tool_call(
					function_name=function_name,
					arguments_raw=arguments_raw,
					chat=chat,
					portfolio=portfolio,
					security=security,
				)

				result_content = json.dumps(tool_result, ensure_ascii=False, default=str)
				if len(result_content) > tool_result_max_chars:
					result_content = result_content[:tool_result_max_chars] + "..."

				messages.append({
					"role": "tool",
					"tool_call_id": call_id,
					"name": function_name,
					"content": result_content,
				})

				tool_trace.append({
					"round": round_index,
					"tool": function_name,
					"call_id": call_id,
					"ok": bool(tool_result.get("ok", False)),
					"duration_ms": round((time.time() - call_started) * 1000, 2),
					"args": tool_result.get("args", {}),
					"error": tool_result.get("error"),
				})

				self._publish_chat_realtime(
					event_name='cf_streaming_update',
					payload={
						'message_id': self.name,
						'chat_id': self.chat,
						'message': f"[Tool] {function_name} executed",
						'reasoning': "\n\n".join(all_reasoning_parts),
						'status': 'streaming'
					}
				)

		raise RuntimeError(f"Tool-call chain exceeded max rounds ({max_rounds})")

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
			"max_tokens": self._get_max_completion_tokens(settings),
			"tools": tools,
		}
		if not self._is_reasoner_model(self.model):
			params["temperature"] = 1.0

		max_retries = self._get_max_api_retries(settings)
		retry_backoff_base_seconds = self._get_retry_backoff_base_seconds(settings)
		for attempt in range(1, max_retries + 1):
			try:
				return client.chat.completions.create(**params)
			except Exception as exc:
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

	def _tool_calls_enabled(self, settings):
		raw = settings.get("tool_calls_enabled")
		if raw is None:
			return bool(TOOL_CALLS_ENABLED_DEFAULT)
		return bool(int(raw))

	def _get_max_tool_rounds(self, settings):
		return max(1, self._read_int_setting(settings, "max_tool_rounds", DEFAULT_MAX_TOOL_ROUNDS))

	def _get_max_tool_calls_per_round(self, settings):
		return max(1, self._read_int_setting(settings, "max_tool_calls_per_round", DEFAULT_MAX_TOOL_CALLS_PER_ROUND))

	def _get_tool_result_max_chars(self, settings):
		return max(500, self._read_int_setting(settings, "tool_result_max_chars", DEFAULT_TOOL_RESULT_MAX_CHARS))

	def _get_tool_definitions(self):
		return [
			{
				"type": "function",
				"function": {
					"name": "get_security_snapshot",
					"description": "Get market and recommendation snapshot for one security.",
					"parameters": {
						"type": "object",
						"properties": {
							"identifier": {"type": "string", "description": "Security symbol, name, or ISIN"},
							"include_news": {"type": "boolean", "description": "Include latest parsed news items"},
							"news_limit": {"type": "integer", "description": "Max news items to include"},
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
							"portfolio": {"type": "string", "description": "Portfolio name"},
							"limit": {"type": "integer", "description": "Max holdings to return"},
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
							"identifier": {"type": "string", "description": "Security symbol, name, or ISIN"},
							"limit": {"type": "integer", "description": "Max number of items"},
						},
						"required": ["identifier"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "web_search",
					"description": "Search the web and return top textual snippets.",
					"parameters": {
						"type": "object",
						"properties": {
							"query": {"type": "string", "description": "Search query"},
							"max_results": {"type": "integer", "description": "Max results to return"},
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
							"url": {"type": "string", "description": "HTTP or HTTPS URL"},
							"max_chars": {"type": "integer", "description": "Maximum characters in returned content"},
						},
						"required": ["url"],
					},
				},
			},
		]

	def _execute_tool_call(self, function_name, arguments_raw, chat, portfolio, security):
		args = self._safe_json_loads(arguments_raw, default={})
		if not isinstance(args, dict):
			args = {}

		handlers = {
			"get_security_snapshot": lambda: self._tool_get_security_snapshot(args, security),
			"get_portfolio_holdings": lambda: self._tool_get_portfolio_holdings(args, portfolio),
			"get_latest_security_news": lambda: self._tool_get_latest_security_news(args, security),
			"web_search": lambda: self._tool_web_search(args),
			"fetch_url_content": lambda: self._tool_fetch_url_content(args),
		}

		if function_name not in handlers:
			return {"ok": False, "args": args, "error": f"Unknown tool: {function_name}"}

		try:
			result = handlers[function_name]()
			return {"ok": True, "args": args, "result": result}
		except Exception as exc:
			frappe.log_error(title=f"Tool call failed: {function_name}", message=str(exc))
			return {"ok": False, "args": args, "error": str(exc)}

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
		extracted = fetch_and_embed_url_content(url, self)
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
		results = self._search_web_results(query, num_results=max_results)
		return {
			"query": query,
			"count": len(results),
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

	def _build_chat_completion_params(self, messages, settings):
		params = {
			"model": self.model,
			"messages": messages,
			"stream": True,
			"max_tokens": self._get_max_completion_tokens(settings),
		}

		if not self._is_reasoner_model(self.model):
			params["temperature"] = 1.0

		return params

	def _create_streaming_completion_with_retry(self, client, messages, settings):
		params = self._build_chat_completion_params(messages, settings)
		max_retries = self._get_max_api_retries(settings)
		retry_backoff_base_seconds = self._get_retry_backoff_base_seconds(settings)

		for attempt in range(1, max_retries + 1):
			try:
				return client.chat.completions.create(**params)
			except Exception as exc:
				if attempt >= max_retries or not self._is_retryable_error(exc):
					raise

				sleep_seconds = retry_backoff_base_seconds * (2 ** (attempt - 1))
				frappe.logger("cognitive_folio").warning(
					"Transient chat API error for %s (attempt %s/%s): %s",
					self.name,
					attempt,
					max_retries,
					str(exc),
				)
				time.sleep(sleep_seconds)

		raise RuntimeError("Failed to create streaming chat completion")

	def _is_reasoner_model(self, model_name):
		return (model_name or "").startswith("deepseek-reasoner")

	def _get_max_completion_tokens(self, settings):
		if self._is_reasoner_model(self.model):
			default_tokens = self._read_int_setting(settings, "reasoner_default_max_tokens", DEFAULT_REASONER_MAX_TOKENS)
			max_cap = self._read_int_setting(settings, "reasoner_max_tokens_cap", MAX_REASONER_MAX_TOKENS)
			return max(1, min(default_tokens, max_cap))

		default_tokens = self._read_int_setting(settings, "chat_default_max_tokens", DEFAULT_CHAT_MAX_TOKENS)
		max_cap = self._read_int_setting(settings, "chat_max_tokens_cap", MAX_CHAT_MAX_TOKENS)
		return max(1, min(default_tokens, max_cap))

	def _get_max_context_tokens(self, settings):
		return max(1, self._read_int_setting(settings, "max_context_tokens", MAX_CONTEXT_TOKENS))

	def _get_max_api_retries(self, settings):
		return max(1, self._read_int_setting(settings, "max_api_retries", MAX_OPENAI_RETRIES))

	def _get_retry_backoff_base_seconds(self, settings):
		return max(0.1, self._read_float_setting(settings, "retry_backoff_base_seconds", RETRY_BACKOFF_BASE_SECONDS))

	def _get_stream_flush_interval_seconds(self, settings):
		return max(0.1, self._read_float_setting(settings, "stream_flush_interval_seconds", STREAM_FLUSH_INTERVAL_SECONDS))

	def _get_stream_flush_min_char_delta(self, settings):
		return max(1, self._read_int_setting(settings, "stream_flush_min_char_delta", STREAM_FLUSH_MIN_CHAR_DELTA))

	def _read_int_setting(self, settings, fieldname, default_value):
		try:
			value = int(settings.get(fieldname))
			if value <= 0:
				return default_value
			return value
		except (TypeError, ValueError):
			return default_value

	def _read_float_setting(self, settings, fieldname, default_value):
		try:
			value = float(settings.get(fieldname))
			if value <= 0:
				return default_value
			return value
		except (TypeError, ValueError):
			return default_value

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

	def extract_search_query(self, prompt_text=None):
		"""Use OpenAI to intelligently extract search query from prompt"""
		try:
			from openai import OpenAI
			
			settings = frappe.get_single("CF Settings")
			client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
			
			# Create a focused prompt for search query extraction
			extraction_prompt = f"""
You are a search query extraction assistant. Your job is to analyze user prompts and extract the most relevant search terms for a web search.

Rules:
1. Extract 1-3 key search terms or phrases that would be most useful for web search
2. Focus on specific topics, companies, concepts, or current events mentioned
3. Ignore generic words like "tell me about" or "what do you think"
4. If the prompt is about financial analysis, include relevant financial terms
5. Return only the search query, nothing else
6. If no clear search terms can be identified, return the main topic in 2-3 words

User prompt: "{(prompt_text if prompt_text is not None else self.prompt)[:500]}"

Search query:"""

			response = client.chat.completions.create(
				model="deepseek-chat",
				messages=[{"role": "user", "content": extraction_prompt}],
				max_tokens=50,
				temperature=0.1  # Low temperature for consistent extraction
			)
			
			search_query = response.choices[0].message.content.strip()
			
			# Clean up the response (remove quotes, extra punctuation)
			search_query = search_query.strip('"\'.,!?')
			
			# Fallback if extraction failed
			if not search_query or len(search_query) < 3:
				source_prompt = prompt_text if prompt_text is not None else self.prompt
				return (source_prompt or "")[:50].strip()
				
			return search_query
			
		except Exception as e:
			frappe.log_error(f"Search query extraction error: {str(e)}", "Search Query Extraction")
			# Fallback to simple extraction
			source_prompt = prompt_text if prompt_text is not None else self.prompt
			return (source_prompt or "")[:50].strip()

	def perform_web_search(self, query, num_results=3):
		"""Perform web search and return snippets-only context for the model prompt."""
		results = self._search_web_results(query, num_results=num_results)
		if not results:
			return ""

		snippets = []
		for result in results:
			snippet = (result.get('snippet') or '').strip()
			if not snippet:
				continue
			if len(snippet) > 240:
				snippet = snippet[:240] + "..."
			snippets.append(snippet)

		if not snippets:
			return ""

		lines = ["Web snippets:"]
		for i, snippet in enumerate(snippets, 1):
			lines.append(f"{i}. {snippet}")

		return "\n".join(lines)

	def _search_web_results(self, query, num_results=3):
		"""Return normalized web search results with a minimal DDGS-only implementation."""
		try:
			from duckduckgo_search import DDGS
		except ImportError:
			frappe.log_error("duckduckgo_search package not installed", "Web Search Error")
			return []

		try:
			with DDGS() as ddgs:
				raw_results = list(ddgs.text(query, max_results=num_results))
		except Exception as e:
			frappe.log_error(f"Web search error: {str(e)}", "Web Search Error")
			return []

		normalized = []
		for result in raw_results or []:
			if not isinstance(result, dict):
				continue
			title = (result.get('title') or '').strip()
			url = (result.get('href') or '').strip()
			snippet = (result.get('body') or '').strip()
			if not url:
				continue
			if len(snippet) > 500:
				snippet = snippet[:500] + "..."
			normalized.append({
				"title": title or "Untitled",
				"url": url,
				"snippet": snippet,
				"source": "ddgs",
			})

		return normalized
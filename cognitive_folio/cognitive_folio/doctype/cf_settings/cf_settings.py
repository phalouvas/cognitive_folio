# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
from urllib.parse import urljoin
import json

class CFSettings(Document):
	def validate(self):
		self.deployment_environment = (self.deployment_environment or "production").strip().lower()
		if self.deployment_environment == "":
			self.deployment_environment = "production"

		if self.feature_flags_json not in (None, ""):
			try:
				parsed_flags = json.loads(self.feature_flags_json)
			except Exception:
				frappe.throw("Feature Flags JSON must be valid JSON.")

			if not isinstance(parsed_flags, dict):
				frappe.throw("Feature Flags JSON must be a JSON object.")

		self.max_context_tokens = self._coerce_int(self.max_context_tokens, 120000, 1, 200000)
		self.chat_default_max_tokens = self._coerce_int(self.chat_default_max_tokens, 4000, 1, 64000)
		self.reasoner_default_max_tokens = self._coerce_int(self.reasoner_default_max_tokens, 32000, 1, 128000)
		self.chat_max_tokens_cap = self._coerce_int(self.chat_max_tokens_cap, 8000, 1, 128000)
		self.reasoner_max_tokens_cap = self._coerce_int(self.reasoner_max_tokens_cap, 64000, 1, 128000)
		self.max_api_retries = self._coerce_int(self.max_api_retries, 5, 1, 10)
		self.retry_backoff_base_seconds = self._coerce_float(self.retry_backoff_base_seconds, 1.5, 0.1, 30.0)
		self.stream_flush_interval_seconds = self._coerce_float(self.stream_flush_interval_seconds, 0.5, 0.1, 10.0)
		self.stream_flush_min_char_delta = self._coerce_int(self.stream_flush_min_char_delta, 120, 1, 5000)
		self.max_tool_rounds = self._coerce_int(self.max_tool_rounds, 6, 1, 30)
		self.max_tool_calls_per_round = self._coerce_int(self.max_tool_calls_per_round, 4, 1, 30)
		self.tool_result_max_chars = self._coerce_int(self.tool_result_max_chars, 8000, 500, 40000)

		self.web_search_max_results = self._coerce_int(
			self.web_search_max_results, 5, 1, 20
		)
		if not (self.web_search_providers or "").strip():
			self.web_search_providers = "ddgs"

		if not (self.default_ai_model or "").strip():
			self.default_ai_model = "deepseek-reasoner"

		self.thinking_budget_tokens = self._coerce_int(self.thinking_budget_tokens, 2048, 128, 64000)
		self.top_p = self._coerce_float(self.top_p, 0.8, 0.0, 1.0, allow_zero=True)
		self.frequency_penalty = self._coerce_float(self.frequency_penalty, 0.0, -2.0, 2.0, allow_zero=True)
		self.presence_penalty = self._coerce_float(self.presence_penalty, 0.0, -2.0, 2.0, allow_zero=True)

		seed_value = self.seed_value
		if seed_value not in (None, ""):
			self.seed_value = self._coerce_int(seed_value, 0, 0, 2147483647)

		if (self.thinking_type or "").strip() == "":
			self.thinking_type = "adaptive"
		else:
			# Validate thinking_type is one of the values accepted by OpenAI API
			valid_types = {"adaptive", "enabled", "disabled"}
			if self.thinking_type.lower() not in valid_types:
				frappe.throw(f"Thinking Type must be one of: {', '.join(sorted(valid_types))}")

	@frappe.whitelist()
	def check_openwebui_connection(self):

		try:
			from openai import OpenAI			
		except ImportError:
			frappe.msgprint("OpenAI package is not installed. Please run 'bench pip install openai'")
			return 0
		
		try:
			client = OpenAI(api_key=self.get_password('open_ai_api_key'), base_url=self.open_ai_url)
			response = client.models.list()
			self.update_ai_models(response.data)
			self.save()
			return {'success': True}
		except requests.exceptions.RequestException as e:
			return {'success': False, 'error': str(e)}
		except Exception as e:
			return {'success': False, 'error': str(e)}
	
	def update_ai_models(self, response_data):
		try:
			
			# Clear existing models
			self.ai_models = []
			
			# Add new models from response
			for model_data in response_data:
				# Create a new row for each model
				model = {
					'model_id': model_data.id,
					'object_type': model_data.object,
					'owned_by': model_data.owned_by
				}
				
				self.append('ai_models', model)
			
			frappe.msgprint(f"Successfully updated {len(self.ai_models)} AI models")
			
		except Exception as e:
			frappe.log_error(f"Error updating AI models: {str(e)}", "CF Settings")
			raise

	def _coerce_int(self, value, default, min_value, max_value):
		try:
			parsed = int(value)
		except (TypeError, ValueError):
			return default
		return max(min_value, min(max_value, parsed))

	def _coerce_float(self, value, default, min_value, max_value, allow_zero=False):
		try:
			parsed = float(value)
		except (TypeError, ValueError):
			return default

		if not allow_zero and parsed <= 0:
			return default

		return max(min_value, min(max_value, parsed))
import frappe
from frappe.model.document import Document
import re
import datetime
from cognitive_folio.utils.markdown import safe_markdown_to_html
from cognitive_folio.utils.helper import replace_variables
from cognitive_folio.utils.url_fetcher import fetch_and_embed_url_content

class CFChatMessage(Document):

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
			timeout=900,
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
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'message_id': message_doc.name,
					'chat_id': message_doc.chat,
					'status': 'success',
					'message': f"Response ready for message {message_doc.name}"
				},
				user=message_doc.owner
			)
		except Exception as e:
			import traceback
			error_message = str(e)
			full_traceback = traceback.format_exc()
			frappe.log_error(title=f"Chat Message Processing Error: {self.name}", message=f"{error_message}\n\nFull Traceback:\n{full_traceback}")
			
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
				frappe.publish_realtime(
					event='cf_job_completed',
					message={
						'message_id': self.name,  # Use self.name as fallback
						'chat_id': getattr(message_doc, 'chat', self.chat),  # Use message_doc if available, else self
						'status': 'error',
						'message': f"Error processing message {self.name}: {error_message}"
					},
					user=getattr(message_doc, 'owner', self.owner)  # Use message_doc owner if available, else self
				)
			except Exception as notify_e:
				# Last resort - log that we couldn't even notify the user
				frappe.log_error(title=f"Failed to notify user of chat error: {self.name}", 
							   message=f"Original error: {error_message}\nNotification error: {str(notify_e)}")

	def send(self):
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
		settings = frappe.get_single("CF Settings")
		client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
	
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
		max_context_tokens = 60000  # Leave buffer for response
		available_tokens = max_context_tokens - system_tokens
		
		# Process current message prompt first to know how much space it needs
		self.prompt = self.prepare_prompt(portfolio, security)

		# Detect URLs and embed their content (guarded by optional checkbox)
		if getattr(self, 'fetch_urls', False):
			try:
				self.prompt = fetch_and_embed_url_content(self.prompt, self)
			except Exception as e:
				frappe.log_error(f"URL embedding failed for message {self.name}: {str(e)}", "URL Fetch Error")
		
		# Extract file content from attachments (PDF with tables, or plain text for other formats)
		try:
			self.prompt = self.extract_file_content()
		except Exception as e:
			frappe.log_error(f"File extraction failed for message {self.name}: {str(e)}", "File Extraction Error")
		
		# NEW: Perform web search if checkbox is enabled
		if getattr(self, 'web_search', False):  # Check if web_search field exists and is True
			try:
				# Use OpenAI to extract intelligent search query
				search_query = self.extract_search_query()
				if search_query:
					search_results = self.perform_web_search(search_query)
					# Prepend search results to the prompt
					self.prompt = f"{search_results}\n\n--- User Query ---\n{self.prompt}"
			except Exception as e:
				frappe.log_error(f"Web search failed for message {self.name}: {str(e)}", "Web Search Error")
				# Continue without web search if it fails
    
		# Final safety check: ensure self.prompt is a string before encoding
		if not isinstance(self.prompt, str):
			frappe.log_error(title=f"Prompt type error in message {self.name}", 
							message=f"self.prompt is type {type(self.prompt)}, value: {repr(self.prompt)}")
			self.prompt = str(self.prompt) if self.prompt is not None else ""
		
		current_prompt_tokens = len(encoding.encode(self.prompt))
		available_tokens -= current_prompt_tokens
		
		# Add previous messages while staying within token limit
		used_tokens = 0
		for message in chat_messages:  # Already ordered in most recent first order
			user_tokens = len(encoding.encode(message.prompt))
			assistant_tokens = len(encoding.encode(message.response))
			message_tokens = user_tokens + assistant_tokens
			
			if used_tokens + message_tokens > available_tokens:
				break  # Stop adding messages if we exceed token limit
				
			# Insert at position 1 to maintain chronological order (after system message)
			messages.insert(1, {"role": "user", "content": message.prompt})
			messages.insert(2, {"role": "assistant", "content": message.response})
			used_tokens += message_tokens
		
		# Add current message
		messages.append({"role": "user", "content": self.prompt})
	
		# Enable streaming
		response = client.chat.completions.create(
			model=self.model,
			messages=messages,
			stream=True,  # Enable streaming
			temperature=0.2
		)
	
		# Initialize response variables
		full_response = ""
		reasoning_content = ""
		
		# Process streaming chunks
		for chunk in response:
			if chunk.choices and len(chunk.choices) > 0:
				choice = chunk.choices[0]
				content_updated = False
				
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
					# Update the document with the current partial response
					self.response = full_response
					self.response_html = safe_markdown_to_html(full_response)
					self.reasoning = reasoning_content
					
					# Save the partial response to database
					self.db_update()
					frappe.db.commit()
					
					# Notify frontend to reload the frame
					frappe.publish_realtime(
						event='cf_streaming_update',
						message={
							'message_id': self.name,
							'chat_id': self.chat,
							'message': full_response,
							'reasoning': reasoning_content,
							'status': 'streaming'
						},
						user=self.owner
					)
					
		# Final update with complete response
		self.response = full_response
		self.response_html = safe_markdown_to_html(full_response)
		self.reasoning = reasoning_content
		
		# Note: tokens might not be available in streaming mode
		# You might need to calculate them manually or handle differently
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

	def detect_natural_language_comparisons(self, prompt, security):
		"""Detect natural language comparison queries and transform them to comparison syntax"""
		# Pattern: "compare <period1> vs/to/and <period2>"
		# Examples: "compare Q3 vs Q2", "compare 2024 to 2023", "compare Q3 2024 and Q2 2024"
		
		# Ensure prompt is a string
		if not prompt or not isinstance(prompt, str):
			return ""
		
		patterns = [
			# Quarterly: "Q3 vs Q2", "Q3 2024 vs Q2 2024"
			r'compare\s+(?:Q|q)(\d)\s+(\d{4})?\s*(?:vs|to|and)\s+(?:Q|q)(\d)\s+(\d{4})?',
			r'compare\s+(?:Q|q)(\d)\s*(?:vs|to|and)\s+(?:Q|q)(\d)',
			# Annual: "2024 vs 2023", "compare 2024 to 2023"
			r'compare\s+(\d{4})\s*(?:vs|to|and)\s+(\d{4})',
			# Quarter vs previous: "Q3 vs previous quarter"
			r'compare\s+(?:Q|q)(\d)(?:\s+(\d{4}))?\s*(?:vs|to|and)\s+(?:previous|last)\s+quarter',
			# Year vs previous: "2024 vs previous year"
			r'compare\s+(\d{4})\s*(?:vs|to|and)\s+(?:previous|last)\s+year',
		]
		
		modified = prompt
		
		for pattern in patterns:
			match = re.search(pattern, modified, re.IGNORECASE)
			if match:
				groups = match.groups()
				
				if 'Q' in match.group(0) or 'q' in match.group(0):
					# Quarterly comparison
					if len(groups) >= 3:
						q1, year1, q2, year2 = groups if len(groups) == 4 else (groups[0], groups[1], groups[2], None)
						
						# Handle cases where year is not specified
						if not year1 and not year2:
							# Use current year
							import datetime
							current_year = datetime.datetime.now().year
							year1 = year2 = current_year
						elif year1 and not year2:
							year2 = year1
						elif year2 and not year1:
							year1 = year2
						
						period1 = f"{year1}Q{q1}"
						period2 = f"{year2}Q{q2}"
						
						if security:
							replacement = f"{{{{periods:compare:{period1}:{period2}}}}}"
						else:
							replacement = f"((periods:compare:{period1}:{period2}))"
						
						modified = modified[:match.start()] + replacement + modified[match.end():]
					elif 'previous' in match.group(0).lower() or 'last' in match.group(0).lower():
						# Handle "Q3 vs previous quarter"
						q1 = groups[0]
						year = groups[1] if len(groups) > 1 and groups[1] else datetime.datetime.now().year
						
						# Calculate previous quarter
						q1_int = int(q1)
						if q1_int == 1:
							q2 = 4
							year2 = int(year) - 1
						else:
							q2 = q1_int - 1
							year2 = year
						
						period1 = f"{year}Q{q1}"
						period2 = f"{year2}Q{q2}"
						
						if security:
							replacement = f"{{{{periods:compare:{period1}:{period2}}}}}"
						else:
							replacement = f"((periods:compare:{period1}:{period2}))"
						
						modified = modified[:match.start()] + replacement + modified[match.end():]
				else:
					# Annual comparison
					if len(groups) >= 2:
						year1, year2 = groups[0], groups[1] if len(groups) > 1 else None
						
						if year2:
							period1 = year1
							period2 = year2
						elif 'previous' in match.group(0).lower() or 'last' in match.group(0).lower():
							period1 = year1
							period2 = str(int(year1) - 1)
						else:
							continue
						
						if security:
							replacement = f"{{{{periods:compare:{period1}:{period2}}}}}"
						else:
							replacement = f"((periods:compare:{period1}:{period2}))"
						
						modified = modified[:match.start()] + replacement + modified[match.end():]
				
				break  # Process one comparison at a time
		
		return modified

	def prepare_prompt(self, portfolio, security):
		"""Prepare the prompt with variable replacements"""
		try:
			# First, detect and transform natural language comparisons (Task 5.3)
			# Ensure self.prompt is a string
			if not self.prompt or not isinstance(self.prompt, str):
				self.prompt = ""
			prompt = self.detect_natural_language_comparisons(self.prompt, security)
		except Exception as e:
			import traceback
			frappe.log_error(title=f"Error in detect_natural_language_comparisons: {self.name}", 
							message=f"prompt type: {type(self.prompt)}, value: {self.prompt}\n{traceback.format_exc()}")
			raise
		
		# --- Comparison helpers (Task 2.5) ---
		def _parse_period_label(label):
			label = label.strip()
			quarter = ""
			if "Q" in label:
				parts = label.split("Q")
				try:
					year = int(parts[0])
					q_part = "Q" + parts[1]
					if q_part in ["Q1","Q2","Q3","Q4"]:
						quarter = q_part
					period_type = "Quarterly"
				except Exception:
					return None
			else:
				try:
					year = int(label)
					period_type = "Annual"
				except Exception:
					return None
			return {"year": year, "quarter": quarter, "period_type": period_type}

		def _fetch_period(security_name, spec):
			if not spec:
				return None
			filters = {"security": security_name, "period_type": spec["period_type"], "fiscal_year": spec["year"]}
			if spec["period_type"] == "Quarterly":
				filters["fiscal_quarter"] = spec["quarter"]
			return frappe.get_all(
				"CF Financial Period",
				filters=filters,
				fields=["fiscal_year","fiscal_quarter","total_revenue","net_income","gross_margin","operating_margin","net_margin"],
				limit=1
			)

		def _format_compare(current, previous, security_label):
			if not current or not previous:
				return f"[Insufficient data to compare for {security_label}]"
			c = current[0]; p = previous[0]
			rev_c = c.total_revenue or 0; rev_p = p.total_revenue or 0
			ni_c = c.net_income or 0; ni_p = p.net_income or 0
			gm_c = c.gross_margin or 0; gm_p = p.gross_margin or 0
			om_c = c.operating_margin or 0; om_p = p.operating_margin or 0
			nm_c = c.net_margin or 0; nm_p = p.net_margin or 0
			def pct_change(new, old):
				return ((new - old)/old*100) if old else 0
			lines = [f"### Comparison for {security_label}"]
			lines.append(f"Current Period: {c.fiscal_year}{(' '+c.fiscal_quarter) if c.fiscal_quarter else ''}")
			lines.append(f"Previous Period: {p.fiscal_year}{(' '+p.fiscal_quarter) if p.fiscal_quarter else ''}")
			lines.append("")
			lines.append("**Revenue & Net Income:**")
			lines.append(f"- Revenue: ${rev_c:,.2f} (Prev: ${rev_p:,.2f}, Change: {pct_change(rev_c, rev_p):+.2f}%)")
			lines.append(f"- Net Income: ${ni_c:,.2f} (Prev: ${ni_p:,.2f}, Change: {pct_change(ni_c, ni_p):+.2f}%)")
			lines.append("")
			lines.append("**Margins (percentage points):**")
			lines.append(f"- Gross Margin: {gm_c:.2f}% (Prev: {gm_p:.2f}%, Δ: {(gm_c-gm_p):+.2f}pp)")
			lines.append(f"- Operating Margin: {om_c:.2f}% (Prev: {om_p:.2f}%, Δ: {(om_c-om_p):+.2f}pp)")
			lines.append(f"- Net Margin: {nm_c:.2f}% (Prev: {nm_p:.2f}%, Δ: {(nm_c-nm_p):+.2f}pp)")
			return "\n".join(lines)

		def _replace_security_compare(m):
			if not security:
				return "[No security context for comparison]"
			parts = m.group(1).split(":")
			if len(parts) < 2:
				return "[Compare syntax requires two period labels]"
			label_a = _parse_period_label(parts[0])
			label_b = _parse_period_label(parts[1])
			if not label_a or not label_b:
				return "[Invalid period labels for comparison]"
			try:
				cur = _fetch_period(security.name, label_a)
				prev = _fetch_period(security.name, label_b)
				return _format_compare(cur, prev, security.security_name or security.name)
			except Exception as e:
				frappe.log_error(f"Security compare expansion error: {e}")
				return f"[Error expanding security comparison: {e}]"

		def _replace_portfolio_compare(m):
			if not portfolio:
				return "[No portfolio context for comparison]"
			parts = m.group(1).split(":")
			if len(parts) < 2:
				return "[Compare syntax requires two period labels]"
			label_a = _parse_period_label(parts[0])
			label_b = _parse_period_label(parts[1])
			if not label_a or not label_b:
				return "[Invalid period labels for comparison]"
			try:
				# Holdings
				holdings = frappe.get_all("CF Portfolio Holding", filters={"portfolio": portfolio.name}, fields=["name","security"])
				sections = [f"### Portfolio Comparison ({parts[0]} vs {parts[1]})"]
				agg_current_rev = agg_previous_rev = 0
				agg_current_gm = agg_previous_gm = 0
				for h in holdings:
					try:
						sec_doc = frappe.get_doc("CF Security", h.security)
						cur = _fetch_period(sec_doc.name, label_a)
						prev = _fetch_period(sec_doc.name, label_b)
						comp = _format_compare(cur, prev, sec_doc.security_name or sec_doc.name)
						sections.append(comp)
						if cur and prev:
							c = cur[0]; p = prev[0]
							rev_c = c.total_revenue or 0; rev_p = p.total_revenue or 0
							gm_c = (c.gross_margin or 0); gm_p = (p.gross_margin or 0)
							agg_current_rev += rev_c; agg_previous_rev += rev_p
							agg_current_gm += gm_c * rev_c; agg_previous_gm += gm_p * rev_p
					except Exception:
						continue
					sections.append("")
				if agg_current_rev and agg_previous_rev:
					weighted_gm_current = (agg_current_gm / agg_current_rev) if agg_current_rev else 0
					weighted_gm_previous = (agg_previous_gm / agg_previous_rev) if agg_previous_rev else 0
					sections.insert(1, f"**Aggregate Weighted Gross Margin Change:** {weighted_gm_current:.2f}% vs {weighted_gm_previous:.2f}% (Δ {(weighted_gm_current-weighted_gm_previous):+.2f}pp)")
				return "\n\n".join(sections)
			except Exception as e:
				frappe.log_error(f"Portfolio compare expansion error: {e}")
				return f"[Error expanding portfolio comparison: {e}]"
		
		# --- Relative period resolution helpers (Task 2.1, 2.2) ---
		def _resolve_relative_period(security_name, relative_spec):
			"""
			Resolve relative period specifications to actual period identifiers.
			
			Args:
				security_name: Name of CF Security
				relative_spec: One of:
					- latest_annual, previous_annual, annual_minus_2, annual_minus_3
					- latest_quarterly, previous_quarterly, yoy_quarterly
			
			Returns:
				Dict with year, quarter, period_type or None if not found
			"""
			try:
				if "annual" in relative_spec:
					period_type = "Annual"
					
					# Get latest annual period
					latest = frappe.get_all(
						"CF Financial Period",
						filters={"security": security_name, "period_type": period_type},
						fields=["fiscal_year", "fiscal_quarter"],
						order_by="fiscal_year DESC",
						limit=1
					)
					
					if not latest:
						return None
					
					latest_year = latest[0].fiscal_year
					
					if relative_spec == "latest_annual":
						return {"year": latest_year, "quarter": "", "period_type": period_type}
					elif relative_spec == "previous_annual":
						return {"year": latest_year - 1, "quarter": "", "period_type": period_type}
					elif relative_spec == "annual_minus_2":
						return {"year": latest_year - 2, "quarter": "", "period_type": period_type}
					elif relative_spec == "annual_minus_3":
						return {"year": latest_year - 3, "quarter": "", "period_type": period_type}
					elif relative_spec == "annual_minus_4":
						return {"year": latest_year - 4, "quarter": "", "period_type": period_type}
				
				elif "quarterly" in relative_spec:
					period_type = "Quarterly"
					
					# Get latest quarterly period
					latest = frappe.get_all(
						"CF Financial Period",
						filters={"security": security_name, "period_type": period_type},
						fields=["fiscal_year", "fiscal_quarter"],
						order_by="fiscal_year DESC, fiscal_quarter DESC",
						limit=1
					)
					
					if not latest:
						return None
					
					latest_year = latest[0].fiscal_year
					latest_quarter = latest[0].fiscal_quarter
					
					# Parse quarter (Q1, Q2, Q3, Q4)
					if not latest_quarter or not latest_quarter.startswith('Q'):
						return None
					
					q_num = int(latest_quarter[1])
					
					if relative_spec == "latest_quarterly":
						return {"year": latest_year, "quarter": latest_quarter, "period_type": period_type}
					elif relative_spec == "previous_quarterly":
						# Calculate previous quarter (handle year boundary)
						if q_num == 1:
							prev_year = latest_year - 1
							prev_quarter = "Q4"
						else:
							prev_year = latest_year
							prev_quarter = f"Q{q_num - 1}"
						return {"year": prev_year, "quarter": prev_quarter, "period_type": period_type}
					elif relative_spec == "yoy_quarterly":
						# Same quarter, previous year
						return {"year": latest_year - 1, "quarter": latest_quarter, "period_type": period_type}
				
				return None
			except Exception as e:
				frappe.log_error(f"Error resolving relative period '{relative_spec}': {e}")
				return None
		
		def _get_comparison_periods(security_name, spec1, spec2):
			"""
			Get two period specifications for comparison, handling relative references.
			
			Returns:
				Tuple of (period1_spec, period2_spec, error_message)
			"""
			# Check if specs are relative references
			relative_keywords = [
				"latest_annual", "previous_annual", "annual_minus_2", "annual_minus_3", "annual_minus_4",
				"latest_quarterly", "previous_quarterly", "yoy_quarterly"
			]
			
			period1 = None
			period2 = None
			
			# Resolve spec1
			if spec1 in relative_keywords:
				period1 = _resolve_relative_period(security_name, spec1)
				if not period1:
					return None, None, f"Insufficient historical data for {spec1.replace('_', ' ')}"
			else:
				period1 = _parse_period_label(spec1)
			
			# Resolve spec2
			if spec2 in relative_keywords:
				period2 = _resolve_relative_period(security_name, spec2)
				if not period2:
					return None, None, f"Insufficient historical data for {spec2.replace('_', ' ')}"
			else:
				period2 = _parse_period_label(spec2)
			
			if not period1 or not period2:
				return None, None, "Invalid period specifications for comparison"
			
			return period1, period2, None
		
		# Enhanced comparison replacement functions with relative period support
		def _replace_security_compare_enhanced(m):
			if not security:
				return "[No security context for comparison]"
			parts = m.group(1).split(":")
			if len(parts) < 2:
				return "[Compare syntax requires two period labels]"
			
			spec1, spec2 = parts[0].strip(), parts[1].strip()
			
			# Get resolved periods
			period1, period2, error_msg = _get_comparison_periods(security.name, spec1, spec2)
			
			if error_msg:
				return f"[{error_msg}]"
			
			try:
				cur = _fetch_period(security.name, period1)
				prev = _fetch_period(security.name, period2)
				
				if not cur or not prev:
					# Check which one is missing for better error message
					if not cur:
						period1_label = f"{period1['year']}{period1['quarter']}" if period1['quarter'] else str(period1['year'])
						return f"[Insufficient historical data for {period1_label} period]"
					if not prev:
						period2_label = f"{period2['year']}{period2['quarter']}" if period2['quarter'] else str(period2['year'])
						return f"[Insufficient historical data for {period2_label} period]"
				
				return _format_compare(cur, prev, security.security_name or security.name)
			except Exception as e:
				frappe.log_error(f"Security compare expansion error: {e}")
				return f"[Error expanding security comparison: {e}]"

		# Apply comparison expansions before normal periods
		if not isinstance(prompt, str):
			prompt = str(prompt) if prompt else ""
		prompt = re.sub(r'\(\(periods:compare:([^\)]+)\)\)', lambda m: _replace_portfolio_compare(m), prompt)
		if not isinstance(prompt, str):
			prompt = str(prompt) if prompt else ""
		# Use enhanced comparison function with relative period support
		prompt = re.sub(r'\{\{periods:compare:([^}]+)\}\}', lambda m: _replace_security_compare_enhanced(m), prompt)

		# Security-level periods syntax: {{periods:annual:3[:format]}} or quarterly/ttm
		def _replace_security_periods(m):
			if not security:
				return "[No security context for periods]"
			parts = m.group(1).split(":")
			# m.group(1) already excludes initial 'periods:' per regex below; we split after periods:
			period_type = parts[0].capitalize() if parts else "Annual"
			count = 4
			fmt = "markdown"
			if len(parts) > 1 and parts[1].isdigit():
				count = int(parts[1])
			if len(parts) > 2:
				fmt = parts[2]
			try:
				from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import format_periods_for_ai
				return format_periods_for_ai(security.name, period_type=period_type, num_periods=count, format=fmt)
			except Exception as e:
				frappe.log_error(f"Security periods expansion error: {e}")
				return f"[Error expanding security periods: {e}]"

		# Portfolio-level periods syntax: ((periods:annual:3[:format])) and shorthand ((periods:latest))
		def _replace_portfolio_periods(m):
			if not portfolio:
				return "[No portfolio context for periods]"
			instruction = m.group(1)
			parts = instruction.split(":")
			key = parts[0].lower() if parts else "annual"
			fmt = "markdown"
			count = 3
			if key == "latest":
				# Latest annual + last 4 quarterly for each holding
				try:
					from cognitive_folio.cognitive_folio.doctype.cf_portfolio.cf_portfolio import build_portfolio_financial_summary
					from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import format_periods_for_ai
					# Build holdings list
					holdings = frappe.get_all(
						"CF Portfolio Holding",
						filters={"portfolio": portfolio.name},
						fields=["name", "security"]
					)
					summary = build_portfolio_financial_summary(portfolio, holdings)
					sections = [summary, "", "### Latest Annual + Quarterly Overview"]
					for h in holdings:
						try:
							sec_doc = frappe.get_doc("CF Security", h.security)
							annual_block = format_periods_for_ai(sec_doc.name, period_type="Annual", num_periods=1, format="markdown")
							q_block = format_periods_for_ai(sec_doc.name, period_type="Quarterly", num_periods=4, format="markdown")
							sections.append(f"#### {sec_doc.security_name} ({sec_doc.symbol})\n" + annual_block + "\n" + q_block)
						except Exception:
							continue
					return "\n\n".join(sections)
				except Exception as e:
					frappe.log_error(f"Portfolio latest periods expansion error: {e}")
					return f"[Error expanding portfolio latest periods: {e}]"
			else:
				# Specific period type
				if len(parts) > 1 and parts[1].isdigit():
					count = int(parts[1])
				if len(parts) > 2:
					fmt = parts[2]
				try:
					from cognitive_folio.cognitive_folio.doctype.cf_portfolio.cf_portfolio import build_portfolio_financial_summary
					from cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period import format_periods_for_ai
					holdings = frappe.get_all(
						"CF Portfolio Holding",
						filters={"portfolio": portfolio.name},
						fields=["name", "security"]
					)
					summary = build_portfolio_financial_summary(portfolio, holdings)
					sections = [summary, "", f"### {key.capitalize()} Periods (per holding)"]
					for h in holdings:
						try:
							sec_doc = frappe.get_doc("CF Security", h.security)
							p_block = format_periods_for_ai(sec_doc.name, period_type=key.capitalize(), num_periods=count, format=fmt)
							sections.append(f"#### {sec_doc.security_name} ({sec_doc.symbol})\n" + p_block)
						except Exception:
							continue
					return "\n\n".join(sections)
				except Exception as e:
					frappe.log_error(f"Portfolio periods expansion error: {e}")
					return f"[Error expanding portfolio periods: {e}]"

		# Apply portfolio-level periods first so summary precedes other replacements
		if not isinstance(prompt, str):
			prompt = str(prompt) if prompt else ""
		prompt = re.sub(r'\(\(periods:([^\)]+)\)\)', lambda m: _replace_portfolio_periods(m), prompt)
		# Apply security-level periods
		if not isinstance(prompt, str):
			prompt = str(prompt) if prompt else ""
		prompt = re.sub(r'\{\{periods:([^}]+)\}\}', lambda m: _replace_security_periods(m), prompt)
		
		# Replace ((variable)) with portfolio fields
		if portfolio:
			if not isinstance(prompt, str):
				prompt = str(prompt) if prompt else ""
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
					final_parts.append(str(parts[0]) if parts[0] is not None else "")
					
					for holding_section in all_holding_sections:
						clean_holding_section = holding_section.replace("***HOLDINGS***", "")
						final_parts.append(str(clean_holding_section) if clean_holding_section is not None else "")
					
					if len(parts) > 1:
						final_parts.append(str(parts[-1]) if parts[-1] is not None else "")
					
					prompt = "\n\n".join(final_parts)
		
		elif security:
			if not isinstance(prompt, str):
				prompt = str(prompt) if prompt else ""
			prompt = re.sub(r'\{\{([\w\.]+)\}\}', lambda match: replace_variables(match, security), prompt)
			# Security-level periods already handled above; other variables replaced here
		
		# Final safety check before returning
		if not isinstance(prompt, str):
			prompt = str(prompt) if prompt else ""
		return prompt

	def extract_file_content(self):
		"""Extract content from files referenced in the prompt.
		
		Supports PDF (with table extraction via pdfplumber/PyPDF2) and text files
		(CSV, JSON, XML, TXT, code files, etc.) with encoding auto-detection.
		"""
		try:
			import os
			import html
		except ImportError:
			frappe.log_error("Required modules not available", "File Extraction Error")
			return self.prompt
		
		prompt = self.prompt
		
		# Find all file references BEFORE unescaping (to avoid HTML entity issues)
		# Pattern for normal angle brackets (any file extension)
		# Use a more restrictive pattern that doesn't capture beyond the filename
		normal_pattern = r'<<([^<>]+?\.[a-zA-Z0-9]+)>>'
		file_references = list(re.findall(normal_pattern, prompt, re.IGNORECASE))
		
		# Pattern for HTML encoded angle brackets
		encoded_pattern = r'&lt;&lt;([^&<>]+?\.[a-zA-Z0-9]+)&gt;&gt;'
		file_references.extend(re.findall(encoded_pattern, prompt, re.IGNORECASE))
		
		if not file_references:
			return prompt
		
		# Get all file attachments for current chat message
		files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "CF Chat Message",
				"attached_to_name": self.name
			},
			fields=["file_url", "file_name"]
		)
		
		# Create a mapping of file names to file info
		file_mapping = {}
		for file_info in files:
			file_mapping[file_info.file_name.lower()] = file_info
		
		# Replace each file reference with its content
		for filename in file_references:
			file_key = filename.lower()
			
			if file_key in file_mapping:
				file_info = file_mapping[file_key]
				try:
					# Get the full file path
					file_path = frappe.get_site_path() + file_info.file_url
					
					if os.path.exists(file_path):
						# Determine file type and extract accordingly
						ext = os.path.splitext(filename)[1].lower()
						
						if ext == '.pdf':
							# Extract PDF with table support
							content = self._extract_pdf_with_tables(file_path)
						else:
							# Extract as text file
							content = self._extract_text_file(file_path, file_info.file_name)
							
						if content and content.strip():
							# Replace the reference with the file content
							replacement = f"--- Content of {file_info.file_name} ---\n{content.strip()}\n--- End of {file_info.file_name} ---"
							
							# Replace both normal and encoded versions
							normal_ref = f"<<{filename}>>"
							encoded_ref = f"&lt;&lt;{filename}&gt;&gt;"
							print(f"[DEBUG] Replacing references: '{normal_ref}' and '{encoded_ref}'")
							print(f"[DEBUG] encoded_ref in prompt: {encoded_ref in prompt}")
							prompt = prompt.replace(normal_ref, replacement)
							prompt = prompt.replace(encoded_ref, replacement)
							print(f"[DEBUG] Replacement done")
						else:
							# Replace with message indicating no text found
							no_text_msg = f"[No readable text found in {file_info.file_name}]"
							prompt = prompt.replace(f"<<{filename}>>", no_text_msg)
							prompt = prompt.replace(f"&lt;&lt;{filename}&gt;&gt;", no_text_msg)
				
				except Exception as e:
					frappe.log_error(f"Error extracting content from {file_info.file_name}: {str(e)}", "File Extraction Error")
					# Replace with error message
					error_msg = f"[Error reading {file_info.file_name}]"
					prompt = prompt.replace(f"<<{filename}>>", error_msg)
					prompt = prompt.replace(f"&lt;&lt;{filename}&gt;&gt;", error_msg)
			else:
				# File not found, replace with message
				not_found_msg = f"[File {filename} not found in attachments]"
				prompt = prompt.replace(f"<<{filename}>>", not_found_msg)
				prompt = prompt.replace(f"&lt;&lt;{filename}&gt;&gt;", not_found_msg)
		
		return prompt

	def _extract_pdf_with_tables(self, file_path: str) -> str:
		"""Extract text and tables from PDF, converting tables to markdown.
		
		Tries pdfplumber first for table extraction, falls back to PyPDF2 for text-only.
		
		Args:
			file_path: Path to the PDF file
			
		Returns:
			Markdown-formatted content with tables
		"""
		content_parts = []
		
		# Try pdfplumber first (best for tables)
		try:
			import pdfplumber
			
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
						
		except Exception as e:
			# pdfplumber failed, try PyPDF2
			frappe.log_error(
				title="PDF Extraction Info",
				message=f"pdfplumber failed, trying PyPDF2: {str(e)}"
			)
			
		try:
			import PyPDF2
			
			with open(file_path, 'rb') as file:
				reader = PyPDF2.PdfReader(file)
				
				for page_num in range(len(reader.pages)):
					page = reader.pages[page_num]
					text = page.extract_text()
					
					if text:
						# Remove excessive whitespace
						text = re.sub(r'\n{3,}', '\n\n', text)
						content_parts.append(text)
				
			return "\n\n".join(content_parts)
				
		except Exception as e:
			frappe.log_error(
				title="PDF Extraction Error",
				message=f"Both pdfplumber and PyPDF2 failed: {str(e)}"
			)
			return ""

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

	def _extract_text_file(self, file_path: str, filename: str) -> str:
		"""Extract plain text content from non-PDF files.
		
		Uses encoding fallback chain (UTF-8 → ISO-8859-1 → Windows-1252 → ASCII)
		with final fallback to UTF-8 with error replacement.
		
		Args:
			file_path: Path to the text file
			filename: Original filename for error messages
			
		Returns:
			Plain text content or error message
		"""
		try:
			import os
			
			# File size limit: 20MB
			MAX_TEXT_FILE_SIZE = 20 * 1024 * 1024
			
			# Check if file exists
			if not os.path.exists(file_path):
				return f"[File not found: {filename}]"
			
			# Check file size
			file_size = os.path.getsize(file_path)
			if file_size > MAX_TEXT_FILE_SIZE:
				return f"[File too large: {filename} exceeds 20MB limit]"
			
			# Try common encodings in order
			encodings = ['utf-8', 'iso-8859-1', 'windows-1252', 'ascii']
			content = None
			
			for encoding in encodings:
				try:
					with open(file_path, 'r', encoding=encoding) as f:
						content = f.read()
					break  # Success!
				except (UnicodeDecodeError, LookupError):
					continue
			
			# Final fallback: UTF-8 with error replacement
			if content is None:
				with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
					content = f.read()
			
			# Truncate if content is too large (500K characters)
			if len(content) > 500000:
				content = content[:500000] + "\n\n[Content truncated - file exceeds 500K characters]"
			
			return content
			
		except Exception as e:
			frappe.log_error(f"Text file extraction failed for {filename}: {str(e)}", "File Extraction Error")
			return f"[Unable to extract text from {filename}]"

	def extract_search_query(self):
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

User prompt: "{self.prompt[:500]}"

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
				return self.prompt[:50].strip()
				
			return search_query
			
		except Exception as e:
			frappe.log_error(f"Search query extraction error: {str(e)}", "Search Query Extraction")
			# Fallback to simple extraction
			return self.prompt[:50].strip()

	def perform_web_search(self, query, num_results=3):
		"""Perform web search using DuckDuckGo with OpenAI-extracted query"""
		try:
			from duckduckgo_search import DDGS
			
			with DDGS() as ddgs:
				results = list(ddgs.text(query, max_results=num_results))
				
				if not results:
					return f"No web search results found for query: '{query}'"
				
				formatted = f"--- Web Search Results for '{query}' ---\n\n"
				for i, result in enumerate(results, 1):
					title = result.get('title', 'No title')
					url = result.get('href', 'No URL')
					body = result.get('body', 'No summary')
					
					# Truncate summary if too long
					if len(body) > 300:
						body = body[:300] + "..."
					
					formatted += f"{url}\n"
				
				formatted += "--- End of Web Search Results ---\n"
				return formatted
				
		except ImportError:
			frappe.log_error("DuckDuckGo search package not installed", "Web Search Error")
			return "[Web search unavailable - duckduckgo-search package not installed. Run: bench pip install duckduckgo-search]"
		except Exception as e:
			frappe.log_error(f"Web search error: {str(e)}", "Web Search Error")
			return f"[Web search error: {str(e)}]"
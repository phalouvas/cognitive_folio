# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import json
import os
import requests
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from cognitive_folio.utils.markdown import safe_markdown_to_html
from cognitive_folio.utils.helper import replace_variables, clear_string, get_edgar_data
import re

try:
	import yfinance as yf
	YFINANCE_INSTALLED = True
except ImportError:
	YFINANCE_INSTALLED = False

class CFSecurity(Document):
	def validate(self):

		if self.security_type != "Stock" and not self.symbol:
			self.symbol = self.security_name
			
		if self.security_type == "Cash":
			self.current_price = 1.0

		if self.security_type == "Stock":
			self.validate_isin()
			self.set_news_urls()
		
		self.update_price_alert_status()

	def update_price_alert_status(self):
		"""Update price alert status based on current price vs thresholds"""
		buy_triggered = (
			self.current_price 
			and self.suggestion_buy_price 
			and self.current_price <= self.suggestion_buy_price
		)
		sell_triggered = (
			self.current_price 
			and self.suggestion_sell_price 
			and self.current_price >= self.suggestion_sell_price
		)
		
		if buy_triggered:
			self.price_alert_status = "Buy Signal"
		elif sell_triggered:
			self.price_alert_status = "Sell Signal"
		else:
			self.price_alert_status = ""

	def on_change(self):
		"""Save all holdings"""
		holdings = frappe.get_all(
			"CF Portfolio Holding",
			filters={"security": self.name},
			fields=["name"]
		)
		
		for holding in holdings:
			portfolio_holding = frappe.get_doc("CF Portfolio Holding", holding.name)
			portfolio_holding.save()

	def set_news_urls(self):
		news_urls = []
		if self.news:
			try:
				news_data = json.loads(self.news)
				for item in news_data:
					if 'link' in item:
						news_urls.append(item['link'])
				self.news_html = "\n".join([url for url in news_urls])
			except json.JSONDecodeError:
				frappe.log_error("Invalid JSON format in news data", "CFSecurity News URLs")
	
	def validate_isin(self):
		"""Validate ISIN format if provided"""
		if self.isin:
			# ISIN is a 12-character alphanumeric code
			if len(self.isin) != 12:
				frappe.throw("ISIN must be 12 characters long")
			
			# Basic format validation: 2 letters country code + 9 alphanumeric + 1 check digit
			if not (self.isin[:2].isalpha() and self.isin[2:11].isalnum() and self.isin[11].isalnum()):
				frappe.throw("ISIN format is invalid. It should be 2 letters country code followed by 9 alphanumeric characters and 1 check digit")

	def on_trash(self):
		"""Delete related chats when security is deleted"""
		try:
			# Get all chats related to this security
			related_chats = frappe.get_all(
				"CF Chat",
				filters={"security": self.name},
				fields=["name"]
			)
			
			# Delete each related chat (this will also delete related CF Chat Messages due to cascade)
			for chat in related_chats:
				try:
					frappe.delete_doc("CF Chat", chat.name, force=True)
				except Exception as e:
					frappe.log_error(f"Error deleting chat {chat.name}: {str(e)}", "CF Security Chat Deletion Error")
			
		except Exception as e:
			frappe.log_error(f"Error deleting related chats for security {self.name}: {str(e)}", "CF Security On Trash Error")

	def after_insert(self):
		"""Fetch and set the current price after inserting the document"""
		if YFINANCE_INSTALLED:
			self.fetch_data(with_fundamentals=True)
			self.generate_ai_suggestion()
	
	@frappe.whitelist()
	def fetch_data(self, with_fundamentals=False):
		# Convert string to boolean if needed (frappe.call sends booleans as strings)
		if isinstance(with_fundamentals, str):
			with_fundamentals = with_fundamentals.lower() in ('true', '1', 'yes', 'on')
			
		if self.security_type != "Stock":
			return {'success': False, 'error': _('Not a stock security')}
		
		"""Fetch the current price from Yahoo Finance"""
		try:
			ticker = yf.Ticker(self.symbol)
			ticker_info = ticker.get_info()
			self.ticker_info = frappe.as_json(ticker_info)
			self.currency = ticker_info['currency']
			self.current_price = ticker_info['regularMarketPrice']
			self.news = frappe.as_json(ticker.get_news())
			self.news_urls = "\n".join([item['content']['clickThroughUrl']['url'] for item in json.loads(self.news) if item.get('content') and item['content'].get('clickThroughUrl') and item['content']['clickThroughUrl'].get('url')])
			self.country = ticker_info.get('country', '')
			if with_fundamentals:
				if not self.cik:
					self.fetch_cik()
				if self.cik:
					get_edgar_data(self.cik)
				self.profit_loss = ticker.income_stmt.to_json(date_format='iso')
				self.ttm_profit_loss = ticker.ttm_income_stmt.to_json(date_format='iso')
				self.quarterly_profit_loss = ticker.quarterly_income_stmt.to_json(date_format='iso')
				self.balance_sheet = ticker.balance_sheet.to_json(date_format='iso')
				self.quarterly_balance_sheet = ticker.quarterly_balance_sheet.to_json(date_format='iso')
				self.cash_flow = ticker.cashflow.to_json(date_format='iso')
				self.ttm_cash_flow = ticker.ttm_cashflow.to_json(date_format='iso')
				self.quarterly_cash_flow = ticker.quarterly_cashflow.to_json(date_format='iso')
				self.dividends = ticker.dividends.to_json(date_format='iso')

			if self.country == "South Korea":
				self.country = "Korea, Republic of"
			if not self.region:
				self.region, self.subregion = get_country_region_from_api(self.country)
			self.save()
			
		except Exception as e:
			frappe.log_error(f"Error fetching current price: {str(e)}", "Fetch Current Price Error")
			frappe.throw("Error fetching current price. Please check the symbol.")

	@frappe.whitelist()
	def fetch_cik(self):
		"""Fetch and set CIK using the SEC static ticker lists (single method)."""
		if self.security_type != "Stock":
			return {"success": False, "message": "CIK lookup only applies to stocks."}
		if not self.symbol:
			return {"success": False, "message": "Symbol is required to fetch CIK."}

		ticker = (self.symbol or "").upper()
		try:
			import requests
		except Exception as e:
			return {"success": False, "message": f"requests unavailable: {e}"}

		urls = [
			"https://www.sec.gov/files/company_tickers.json",
			"https://www.sec.gov/files/company_tickers_exchange.json",
		]
		headers = {
			"User-Agent": "cognitive-folio/1.0 (support@kainotomo.com)",
			"Accept": "application/json",
		}
		try:
			for url in urls:
				resp = requests.get(url, headers=headers, timeout=8)
				if resp.status_code != 200:
					continue
				try:
					data = resp.json()
				except Exception:
					continue
				# data can be dict keyed by index or a list; normalize to iterable of entries
				entries = []
				if isinstance(data, dict):
					entries = data.values()
				elif isinstance(data, list):
					entries = data
				for entry in entries:
					try:
						symbol_value = (entry.get("ticker") or "").upper()
						if symbol_value == ticker:
							cik_int = entry.get("cik_str") or entry.get("cik") or entry.get("ciknumber")
							if cik_int:
								self.cik = str(cik_int).zfill(10)
								self.save(ignore_permissions=True)
								return {"success": True, "cik": self.cik}
					except Exception:
						continue
			return {"success": False, "message": "CIK not found for this symbol from SEC list."}
		except Exception as e:
			err_msg = f"CIK lookup failed for {self.symbol}: {str(e)}"
			frappe.log_error(err_msg, "CIK Lookup Error")
			return {"success": False, "message": err_msg}

	@frappe.whitelist()
	def generate_ai_suggestion(self):
		"""Queue AI suggestion generation for the security as a background job"""
		if self.security_type != "Stock":
			return {'success': False, 'error': _('AI suggestion is only for non-stock securities')}
		
		self.ai_suggestion = "Processing your request..."
		self.save()
		
		try:
			from frappe.utils.background_jobs import enqueue
			
			# Create a unique job name to prevent duplicates
			job_name = f"security_ai_suggestion_{self.name}_{frappe.utils.now()}"
			
			# Enqueue the job
			enqueue(
				method="cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.process_security_ai_suggestion",
				queue="long",
				timeout=1800,  # 30 minutes
				job_id=job_name,
				now=False,
				security_name=self.name,
				user=frappe.session.user
			)
			
			frappe.msgprint(
				_("Security AI suggestion generation has been queued. You will be notified when it's complete."),
				alert=True
			)
			
			return {'success': True, 'message': _('Security AI suggestion generation has been queued')}
		
		except Exception as e:
			frappe.log_error(f"Error queueing security AI suggestion: {str(e)}", "Security AI Suggestion Error")
			return {'success': False, 'error': str(e)}
	
	@frappe.whitelist()
	def get_financial_data_coverage(self):
		"""Get available financial data coverage from Yahoo Finance and SEC EDGAR"""
		try:
			from datetime import datetime
			
			coverage_data = {}
			
			# Helper function to parse date and format it
			def format_period(date_str):
				"""Convert ISO date string to readable format (Q3 2024 or FY 2023)"""
				try:
					dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
					year = dt.year
					month = dt.month
					
					# Determine quarter based on month
					if month in [1, 2, 3]:
						return f"Q1 {year}"
					elif month in [4, 5, 6]:
						return f"Q2 {year}"
					elif month in [7, 8, 9]:
						return f"Q3 {year}"
					elif month in [10, 11, 12]:
						return f"Q4 {year}"
				except:
					return date_str
			
			def format_annual_period(date_str):
				"""Convert ISO date string to fiscal year format (FY 2023)"""
				try:
					dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
					return f"FY {dt.year}"
				except:
					return date_str
			
			def extract_periods_from_json(json_field, is_annual=False):
				"""Extract period dates from a JSON field"""
				if not json_field:
					return []
				
				try:
					import json as json_module
					data = json_module.loads(json_field)
					
					if isinstance(data, dict):
						# Get all keys (dates/periods)
						periods = list(data.keys())
						# Format periods
						if is_annual:
							return [format_annual_period(p) for p in periods]
						else:
							return [format_period(p) for p in periods]
				except:
					pass
				
				return []
			
			# Parse Yahoo Finance data
			# Income Statement
			income_statement = {
				'Annual': {},
				'Quarterly': {},
				'TTM': {}
			}
			
			if self.profit_loss:
				periods = extract_periods_from_json(self.profit_loss, is_annual=True)
				if periods:
					income_statement['Annual']['YFinance'] = {
						'count': len(periods),
						'periods': sorted(periods, reverse=True)
					}
			
			if self.quarterly_profit_loss:
				periods = extract_periods_from_json(self.quarterly_profit_loss)
				if periods:
					income_statement['Quarterly']['YFinance'] = {
						'count': len(periods),
						'periods': sorted(periods, reverse=True)
					}
			
			if self.ttm_profit_loss:
				periods = extract_periods_from_json(self.ttm_profit_loss)
				if periods:
					income_statement['TTM']['YFinance'] = {
						'count': len(periods),
						'periods': sorted(periods, reverse=True)
					}
			
			coverage_data['Income Statement'] = income_statement
			
			# Balance Sheet
			balance_sheet = {
				'Annual': {},
				'Quarterly': {}
			}
			
			if self.balance_sheet:
				periods = extract_periods_from_json(self.balance_sheet, is_annual=True)
				if periods:
					balance_sheet['Annual']['YFinance'] = {
						'count': len(periods),
						'periods': sorted(periods, reverse=True)
					}
			
			if self.quarterly_balance_sheet:
				periods = extract_periods_from_json(self.quarterly_balance_sheet)
				if periods:
					balance_sheet['Quarterly']['YFinance'] = {
						'count': len(periods),
						'periods': sorted(periods, reverse=True)
					}
			
			coverage_data['Balance Sheet'] = balance_sheet
			
			# Cash Flow
			cash_flow = {
				'Annual': {},
				'Quarterly': {},
				'TTM': {}
			}
			
			if self.cash_flow:
				periods = extract_periods_from_json(self.cash_flow, is_annual=True)
				if periods:
					cash_flow['Annual']['YFinance'] = {
						'count': len(periods),
						'periods': sorted(periods, reverse=True)
					}
			
			if self.quarterly_cash_flow:
				periods = extract_periods_from_json(self.quarterly_cash_flow)
				if periods:
					cash_flow['Quarterly']['YFinance'] = {
						'count': len(periods),
						'periods': sorted(periods, reverse=True)
					}
			
			if self.ttm_cash_flow:
				periods = extract_periods_from_json(self.ttm_cash_flow)
				if periods:
					cash_flow['TTM']['YFinance'] = {
						'count': len(periods),
						'periods': sorted(periods, reverse=True)
					}
			
			coverage_data['Cash Flow'] = cash_flow
			
			# Fetch and parse SEC EDGAR data if CIK is available
			if self.cik:
				try:
					import json as json_module
					
					# Call get_edgar_data to fetch SEC EDGAR financial statements
					edgar_json = get_edgar_data(
						cik=self.cik,
						annual_years=10,
						quarterly_count=16,
						format='json'
					)
					
					if edgar_json:
						edgar_data = json_module.loads(edgar_json)
						
						# Helper function to extract periods from EDGAR data
						def extract_edgar_periods(statement_data, is_annual=False):
							"""Extract periods from EDGAR statement data"""
							if not statement_data or 'error' in statement_data:
								return []
							
							periods_list = statement_data.get('data', [])
							if not periods_list:
								return []
							
							# Extract column names (periods) from the first data row
							# EDGAR data structure has periods as column headers
							period_dates = []
							
							# Try to get periods from the data structure
							if isinstance(periods_list, list) and len(periods_list) > 0:
								first_row = periods_list[0]
								if isinstance(first_row, dict):
									# Define metadata columns to exclude
									metadata_columns = ['index', 'metric', 'Metric', '', 'label', 'concept']
									
									# Get all keys except metadata columns
									for key in first_row.keys():
										# Skip metadata columns
										if key and key not in metadata_columns:
											period_dates.append(key)
							
							# Format the periods
							formatted_periods = []
							for period in period_dates:
								if is_annual:
									formatted_periods.append(format_annual_period(period))
								else:
									formatted_periods.append(format_period(period))
							
							return formatted_periods
						
						# Parse EDGAR Income Statement
						if 'income_statement_annual' in edgar_data:
							periods = extract_edgar_periods(edgar_data['income_statement_annual'], is_annual=True)
							if periods:
								income_statement['Annual']['EDGAR'] = {
									'count': len(periods),
									'periods': sorted(periods, reverse=True)
								}
						
						if 'income_statement_quarterly' in edgar_data:
							periods = extract_edgar_periods(edgar_data['income_statement_quarterly'])
							if periods:
								income_statement['Quarterly']['EDGAR'] = {
									'count': len(periods),
									'periods': sorted(periods, reverse=True)
								}
						
						# Parse EDGAR Balance Sheet
						if 'balance_sheet_annual' in edgar_data:
							periods = extract_edgar_periods(edgar_data['balance_sheet_annual'], is_annual=True)
							if periods:
								balance_sheet['Annual']['EDGAR'] = {
									'count': len(periods),
									'periods': sorted(periods, reverse=True)
								}
						
						if 'balance_sheet_quarterly' in edgar_data:
							periods = extract_edgar_periods(edgar_data['balance_sheet_quarterly'])
							if periods:
								balance_sheet['Quarterly']['EDGAR'] = {
									'count': len(periods),
									'periods': sorted(periods, reverse=True)
								}
						
						# Parse EDGAR Cash Flow Statement
						if 'cashflow_statement_annual' in edgar_data:
							periods = extract_edgar_periods(edgar_data['cashflow_statement_annual'], is_annual=True)
							if periods:
								cash_flow['Annual']['EDGAR'] = {
									'count': len(periods),
									'periods': sorted(periods, reverse=True)
								}
						
						if 'cashflow_statement_quarterly' in edgar_data:
							periods = extract_edgar_periods(edgar_data['cashflow_statement_quarterly'])
							if periods:
								cash_flow['Quarterly']['EDGAR'] = {
									'count': len(periods),
									'periods': sorted(periods, reverse=True)
								}
						
						# Update coverage data with EDGAR results
						coverage_data['Income Statement'] = income_statement
						coverage_data['Balance Sheet'] = balance_sheet
						coverage_data['Cash Flow'] = cash_flow
						
				except Exception as edgar_error:
					# Log EDGAR errors but don't fail the entire request
					frappe.log_error(f"Error fetching EDGAR data for CIK {self.cik}: {str(edgar_error)}", "EDGAR Data Fetch Error")
			
			return {
				'success': True,
				'data': coverage_data
			}
			
		except Exception as e:
			frappe.log_error(f"Error getting financial data coverage: {str(e)}", "Get Financial Data Coverage Error")
			return {'success': False, 'error': str(e)}
			
	def convert_json_to_markdown(self, data):
		"""Convert JSON data to markdown format for better display"""
		markdown = []
		
		# Add Summary
		if "Summary" in data:
			markdown.append(f"## Summary\n{data['Summary']}\n")
		
		# Add Analysis
		if "Analysis" in data:
			markdown.append(f"## Analysis\n{data['Analysis']}\n")

		# Add Risks
		if "Risks" in data:
			markdown.append(f"## Risks")
			if isinstance(data["Risks"], list):
				for risk in data["Risks"]:
					markdown.append(f"- {risk}")
			else:
				markdown.append(f"{data['Risks']}\n")

		return "\n".join(markdown)

@frappe.whitelist()
def search_stock_symbols(search_term):
	"""Search for stock symbols based on company name or symbol"""
	if not YFINANCE_INSTALLED:
		return {"error": "YFinance package is not installed"}
		
	try:
		# Use Yahoo Finance API for searching
		url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_term}&quotesCount=10"

		headers = {'User-Agent': 'Mozilla/5.0'}
		response = requests.get(url, headers=headers)
		data = response.json()
		
		if "quotes" in data:
			results = []
			for quote in data["quotes"]:
				if quote.get("quoteType") in ["EQUITY", "ETF"]:
					results.append({
						"symbol": quote.get("symbol"),
						"name": quote.get("longname") or quote.get("shortname"),
						"exchange": quote.get("exchange"),
						"type": quote.get("quoteType"),
						"sector": quote.get("sector"),
						"industry": quote.get("industry")
					})
			return {"results": results}
		else:
			return {"error": "No matches found"}
	except Exception as e:
		return {"error": str(e)}

def get_country_region_from_api(country):
	"""Get country region from REST Countries API"""
	country_code = None
	country_code = frappe.get_value("Country", {"country_name": country}, "code")

	try:
		response = requests.get(f"https://restcountries.com/v3.1/alpha/{country_code}")
		if response.status_code == 200:
			data = response.json()
			if data and len(data) > 0:
				return data[0].get('region', 'Unknown'), data[0].get('subregion', 'Unknown')
		return 'Unknown'
	except Exception as e:
		frappe.log_error(f"Error fetching country region: {str(e)}")
		return 'Unknown'
	
@frappe.whitelist()
def process_security_ai_suggestion(security_name, user):
	"""Process AI suggestion for the security (meant to be run as a background job)"""
	try:

		# Get the security document
		security = frappe.get_doc("CF Security", security_name)
		
		if security.security_type == "Cash":
			return False
		
		try:
			from openai import OpenAI            
		except ImportError:
			frappe.log_error("OpenAI package is not installed. Please run 'bench pip install openai'", "AI Suggestion Error")
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'security_id': security_name,
					'status': 'error',
					'error': 'OpenAI package is not installed',
					'message': 'Please run "bench pip install openai" to install the required package.'
				},
				user=user
			)
			return False
		
		try:
			# Get OpenWebUI settings
			settings = frappe.get_single("CF Settings")
			client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
			
			# Use default AI model from settings instead of hardcoded value
			model = settings.default_ai_model or "deepseek-chat"

			prompt = security.ai_prompt or ""

			# Update regex to handle more complex paths including array indices
			prompt = re.sub(r'\{\{([\w\.]+)\}\}', lambda match: replace_variables(match, security), prompt)
			
			messages = [
				{"role": "system", "content": settings.system_content},
				{"role": "user", "content": prompt},
			]
			response = client.chat.completions.create(
				model=model,
				messages=messages,
				stream=False,
				temperature=1.0
			)
			
			# Check if response has choices and content
			if not response.choices or not response.choices[0].message.content:
				raise ValueError("Empty response received from AI model")
			
			content_string = response.choices[0].message.content.strip()
			
			# Validate that we got actual content
			if not content_string:
				raise ValueError("No content in AI response")
			
		except Exception as api_error:
			error_message = f"AI API error: {str(api_error)}"
			frappe.log_error(error_message, "OpenAI API Error")
			
			# Update security with error status
			security.reload()
			security.ai_suggestion = f"❌ **Error generating AI analysis**: {str(api_error)}\n\nPlease try again later or check the AI service configuration."
			security.flags.ignore_version = True
			security.flags.ignore_mandatory = True
			security.save()
			
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'security_id': security_name,
					'status': 'error',
					'error': error_message,
					'message': error_message
				},
				user=user
			)
			
			return False

		try:
			content_string = clear_string(content_string)
			suggestion = json.loads(content_string)

			# Validate the JSON structure
			if not isinstance(suggestion, dict):
				raise ValueError("AI response is not a valid JSON object")

		except json.JSONDecodeError as json_error:
			# If JSON parsing still fails, try a more robust cleanup approach
			try:
				# Remove markdown formatting and fix common JSON issues
				cleaned = content_string.strip()
				
				# Find all string values in the JSON and clean them
				def clean_json_string(match):
					string_content = match.group(1)
					# Replace literal newlines with \n
					string_content = string_content.replace('\n', '\\n')
					# Replace other problematic characters
					string_content = string_content.replace('\r', '\\r')
					string_content = string_content.replace('\t', '\\t')
					string_content = string_content.replace('&nbsp;', ' ')
					# Handle unescaped quotes within strings
					string_content = re.sub(r'(?<!\\)"', '\\"', string_content)
					return f'"{string_content}"'
				
				# Apply cleaning to all JSON string values
				cleaned = re.sub(r'"([^"]*(?:\\.[^"]*)*)"', clean_json_string, cleaned, flags=re.DOTALL)
				
				suggestion = json.loads(cleaned)
				
			except (json.JSONDecodeError, Exception) as secondary_error:
				error_message = f"Invalid JSON in AI response: {str(json_error)}"
				frappe.log_error(f"{error_message}\nRaw response: {content_string}", "AI JSON Parse Error")
				
				# Fallback: save the raw response as markdown
				security.reload()
				security.ai_suggestion = f"⚠️ **AI Analysis** (Raw Response)\n\n{content_string}"
				security.flags.ignore_version = True
				security.flags.ignore_mandatory = True
				security.save()
				
				# Notify user of partial success
				frappe.publish_realtime(
					event='cf_job_completed',
					message={
						'security_id': security_name,
						'status': 'error',
						'error': 'AI response format issue - raw response saved',
						'message': 'AI response had formatting issues but content was saved'
					},
					user=user
				)
				
				return True  # Still consider it a success since we got some response

		except Exception as parse_error:
			error_message = f"Error parsing AI response: {str(parse_error)}"
			frappe.log_error("AI Response Parse Error", error_message)
			
			# Update security with error status
			security.reload()
			security.ai_suggestion = f"❌ **Error processing AI response**: {str(parse_error)}\n\nRaw response saved for debugging."
			security.flags.ignore_version = True
			security.flags.ignore_mandatory = True
			security.save()
			
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'security_id': security_name,
					'status': 'error',
					'error': error_message,
					'message': error_message
				},
				user=user
			)
			
			return False
	
		# Validate the JSON structure has expected fields
		required_sections = ["Evaluation"]
		missing_sections = [section for section in required_sections if section not in suggestion]

		if missing_sections:
			frappe.log_error(f"AI response missing required sections: {missing_sections}", "AI Response Validation Warning")
			# Continue processing with available data

		# Convert JSON to markdown for better display
		markdown_content = security.convert_json_to_markdown(suggestion)

		# Reload the document to get the latest version and avoid modification conflicts
		security.reload()

		# Safely extract values with defaults
		evaluation = suggestion.get("Evaluation", {})
		investment = suggestion.get("Investment", {})
		security.ai_response = content_string
		
		# Extract action from Investment section (new format) or Evaluation (backward compatibility)
		security.suggestion_action = investment.get("Action") or evaluation.get("Recommendation", "")
		security.suggestion_conviction = investment.get("Conviction")
		
		# Extract individual ratings directly from Evaluation (standard format)
		# AI returns 1-10 scale, but Frappe Rating fields use 0.1-1.0 scale (0.1=1 star, 0.2=2 stars, etc.)
		# So divide by 10 and round to 1 decimal place
		try:
			security.rating_moat = round(float(evaluation.get("Moat", 0)) / 10, 1)
			security.rating_management = round(float(evaluation.get("Management", 0)) / 10, 1)
			security.rating_financials = round(float(evaluation.get("Financials", 0)) / 10, 1)
			security.rating_valuation = round(float(evaluation.get("Valuation", 0)) / 10, 1)
			security.rating_industry = round(float(evaluation.get("Industry", 0)) / 10, 1)
			
			# Use the Overall from JSON directly (don't recalculate), convert to 0.1-1.0 scale
			security.suggestion_rating = round(float(evaluation.get("Overall", 0)) / 10, 1)
		except (ValueError, TypeError):
			# Fallback if conversion fails
			security.rating_moat = 0
			security.rating_management = 0
			security.rating_financials = 0
			security.rating_valuation = 0
			security.rating_industry = 0
			security.suggestion_rating = 0
		
		# Extract price targets from Investment section (new format) or Evaluation (backward compatibility)
		security.suggestion_fair_value = investment.get("FairValue") or evaluation.get("Fair Value", 0)
		security.suggestion_buy_price = investment.get("BuyBelowPrice") or evaluation.get("Price Target Buy Below", 0)
		security.suggestion_sell_price = investment.get("SellAbovePrice") or evaluation.get("Price Target Sell Above", 0)
		security.evaluation_stop_loss = investment.get("StopLoss") or evaluation.get("Price Stop Loss", 0)
		security.ai_suggestion = markdown_content
		security.news_reasoning = None
		security.need_evaluation = False
		security.ai_modified = frappe.utils.now_datetime().strftime('%Y-%m-%d %H:%M:%S')
		
		# Use flags to ignore timestamp validation and force save
		security.flags.ignore_version = True
		security.flags.ignore_mandatory = True
		security.save()
		
		# Create CF Chat and CF Chat Message
		chat_doc = frappe.new_doc("CF Chat")
		chat_doc.security = security_name
		chat_doc.title = f"AI Analysis for {security.security_name or security.symbol} @ {frappe.utils.today()}"
		chat_doc.system_prompt = settings.system_content
		chat_doc.save()
		
		# Create the chat message
		message_doc = frappe.new_doc("CF Chat Message")
		message_doc.chat = chat_doc.name
		message_doc.prompt = prompt
		message_doc.response = markdown_content
		message_doc.response_html = safe_markdown_to_html(message_doc.response)
		message_doc.model = model
		message_doc.status = "Success"
		message_doc.system_prompt = settings.system_content
		message_doc.tokens = response.usage.to_json() if hasattr(response, 'usage') else None
		message_doc.flags.ignore_before_save = True
		message_doc.save()
		
		frappe.db.commit()  # Single commit for all changes
		
		# Notify the user that the analysis is complete
		frappe.publish_realtime(
			event='cf_job_completed',
			message={
				'security_id': security_name,
				'status': 'success',
				'chat_id': chat_doc.name,
				'message': f"AI analysis completed for {security.security_name or security.symbol}.",
			},
			user=user
		)
		
		return True
			
	except requests.exceptions.RequestException as e:
		error_message = f"Request error: {str(e)}"
		frappe.log_error("OpenWebUI API Error", error_message)
		
		# Notify user of failure
		frappe.publish_realtime(
			event='cf_job_completed',
			message={
				'security_id': security_name,
				'status': 'error',
				'error': error_message,
				'message': error_message
			},
			user=user
		)
		
		return False
		
	except Exception as e:
		error_message = f"Error generating AI suggestion: {str(e)}"
		
		# Create a short, descriptive title for the error log
		short_title = f"AI Suggestion Error - {security_name}"
		if len(short_title) > 140:
			short_title = f"AI Suggestion Error"[:140]
		
		# FIXED: Correct parameter order - title first, then message
		frappe.log_error(short_title, error_message)
		
		# Notify user of failure
		frappe.publish_realtime(
			event='cf_job_completed',
			message={
				'security_id': security_name,
				'status': 'error',
				'error': error_message[:200],  # Truncate for realtime message too
				'message': error_message[:200]
			},
			user=user
		)
		
		return False

@frappe.whitelist()
def fetch_data_selected(docnames, with_fundamentals=False):
	"""Fetch latest data for selected securities"""
	if isinstance(docnames, str):
		docnames = [d.strip() for d in docnames.strip("[]").replace('"', '').split(",")]
	
	# Convert string to boolean if needed (frappe.call sends booleans as strings)
	if isinstance(with_fundamentals, str):
		with_fundamentals = with_fundamentals.lower() in ('true', '1', 'yes', 'on')
	
	if not docnames:
		frappe.throw(_("Please select at least one Batch"))
	
	total_steps = len(docnames)
	for counter, docname in enumerate(docnames, 1):
		security = frappe.get_doc("CF Security", docname)
		frappe.publish_progress(
			percent=(counter)/total_steps * 100,
			title="Processing",
			description=f"Processing item {counter} of {total_steps} ({security.security_name or security.symbol})",
		)
		security.fetch_data(with_fundamentals=with_fundamentals)
		
	return total_steps

@frappe.whitelist()
def generate_ai_suggestion_selected(docnames):
	"""Fetch latest data for selected securities"""
	if isinstance(docnames, str):
		docnames = [d.strip() for d in docnames.strip("[]").replace('"', '').split(",")]

	if not docnames:
		frappe.throw(_("Please select at least one Batch"))
	
	total_steps = len(docnames)
	for counter, docname in enumerate(docnames, 1):
		security = frappe.get_doc("CF Security", docname)
		frappe.publish_progress(
			percent=(counter)/total_steps * 100,
			title="Processing",
			description=f"Processing item {counter} of {total_steps} ({security.security_name or security.symbol})",
		)
		security.generate_ai_suggestion()
		
	return total_steps

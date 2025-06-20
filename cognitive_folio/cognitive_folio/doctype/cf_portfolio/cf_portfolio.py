import frappe
from frappe.model.document import Document
from frappe.utils import flt, add_days, date_diff
from datetime import datetime, timedelta
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from cognitive_folio.utils.markdown import safe_markdown_to_html
from cognitive_folio.utils.helper import replace_variables, clear_string
import re
import requests
from dateutil import parser as date_parser
from datetime import timezone

class CFPortfolio(Document):
	def validate(self):
		self.validate_disabled_state()
	
	def validate_disabled_state(self):
		"""Handle validations when portfolio is disabled"""
		if self.disabled:
			# Add any validations or actions needed when portfolio is disabled
			pass
	
	def on_update(self):
		"""Update linked records or perform other operations when portfolio is updated"""
		pass
	 
	@frappe.whitelist()
	def evaluate_holdings_news(self):
		"""Evaluate news for all holdings in this portfolio"""
		
		try:
			from frappe.utils.background_jobs import enqueue
			
			# Create a unique job name to prevent duplicates
			job_name = f"portfolio_news_evaluation_{self.name}_{frappe.utils.now()}"
			
			# Enqueue the job
			enqueue(
				method="cognitive_folio.cognitive_folio.doctype.cf_portfolio.cf_portfolio.process_evaluate_holdings_news",
				queue="long",
				timeout=1800,  # 30 minutes
				job_id=job_name,
				now=False,
				portfolio_name=self.name,
				user=frappe.session.user
			)
			
			frappe.msgprint(
				_("Portfolio AI news evaluation has been queued. You will be notified when it's complete."),
				alert=True
			)
			
			return {'success': True, 'message': _('Portfolio AI news evaluation has been queued')}
		
		except Exception as e:
			frappe.log_error(f"Error queueing portfolio AI analysis: {str(e)}", "Portfolio AI Analysis Error")
			return {'success': False, 'error': str(e)}

	@frappe.whitelist()
	def generate_holdings_ai_suggestions(self):
		"""Queue AI suggestion generation for each holding as separate background jobs"""

		try:
			# Get holdings in this portfolio
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters=[
					["portfolio", "=", self.name],
					["security_type", "=", "Stock"]
				],
				fields=["name", "security", "modified"]
			)
			
			if not holdings:
				return {'success': False, 'error': _('No non-cash holdings found in this portfolio')}
			
			# Queue a job for each holding
			for holding in holdings:
				if not holding.security:
					continue
					
				security_obj = frappe.get_doc("CF Security", holding.security)
				security_obj.generate_ai_suggestion()

			return {
				'success': True, 
				'message': _('Queued AI suggestion generation for {0} holdings').format(len(holdings)),
				'count': len(holdings)
			}
				
		except Exception as e:
			frappe.log_error(f"Error queueing AI suggestions for holdings: {str(e)}", "Portfolio Error")
			return {'success': False, 'error': str(e)}
	
	@frappe.whitelist()
	def fetch_holdings_data(self, with_fundamentals=False):
		"""Update prices for all holdings in this portfolio using batch requests"""
		
		# Get all holdings for this portfolio (excluding Cash type securities)
		holdings = frappe.get_all(
			"CF Portfolio Holding",
			filters=[
				["portfolio", "=", self.name],
				["security_type", "=", "Stock"]
			],
			fields=["name", "security"]
		)
		
		if not holdings:
			frappe.msgprint("No holdings found in this portfolio")
			return 0
		
		# Use enumerate to get a counter in the for loop
		total_steps = len(holdings)
		for counter, holding in enumerate(holdings, 1):
			frappe.publish_progress(
				percent=(counter)/total_steps * 100,
				title="Processing",
				description=f"Processing item {counter} of {total_steps} ({holding.security})"
			)
			security = frappe.get_doc("CF Security", holding.security)
			if with_fundamentals:
				security.fetch_data(with_fundamentals=True)
			else:
				security.fetch_data(with_fundamentals=False)
			
		return total_steps
	
	@frappe.whitelist()
	def generate_portfolio_ai_analysis(self):
		"""Queue AI analysis generation for the portfolio as a background job"""

		self.ai_suggestion = "Processing your request..."
		self.ai_suggestion_html = safe_markdown_to_html(self.ai_suggestion)
		self.save()

		try:
			from frappe.utils.background_jobs import enqueue
			
			# Create a unique job name to prevent duplicates
			job_name = f"portfolio_ai_analysis_{self.name}_{frappe.utils.now()}"
			
			# Enqueue the job
			enqueue(
				method="cognitive_folio.cognitive_folio.doctype.cf_portfolio.cf_portfolio.process_portfolio_ai_analysis",
				queue="long",
				timeout=1800,  # 30 minutes
				job_id=job_name,
				now=False,
				portfolio_name=self.name,
				user=frappe.session.user
			)
			
			frappe.msgprint(
				_("Portfolio AI analysis generation has been queued. You will be notified when it's complete."),
				alert=True
			)
			
			return {'success': True, 'message': _('Portfolio AI analysis generation has been queued')}
		
		except Exception as e:
			frappe.log_error(f"Error queueing portfolio AI analysis: {str(e)}", "Portfolio AI Analysis Error")
			return {'success': False, 'error': str(e)}
	
	@frappe.whitelist()
	def update_purchase_prices_from_market(self):
		"""Update average purchase prices for all holdings using closing prices from the portfolio start date"""
		try:
			import yfinance as yf
			from datetime import datetime, timedelta
		except ImportError:
			frappe.msgprint("YFinance package is not installed. Please run 'bench pip install yfinance'")
			return 0
		
		# Check if portfolio has a start date
		if not self.start_date:
			frappe.msgprint("Portfolio doesn't have a start date defined. Please set a start date first.")
			return 0
		
		# Convert start_date to datetime format for yfinance
		start_date_str = self.start_date
		# Add one day to get closing price of the start date
		end_date = datetime.strptime(start_date_str, '%Y-%m-%d') + timedelta(days=1)
		end_date_str = end_date.strftime('%Y-%m-%d')
		
		# Get all holdings for this portfolio
		holdings = frappe.get_all(
			"CF Portfolio Holding",
			filters=[
				["portfolio", "=", self.name],
				["security_type", "==", "Stock"]
			],
			fields=["name", "security"]
		)
		
		if not holdings:
			frappe.msgprint("No holdings found in this portfolio")
			return 0
		
		# Get unique securities and map them to their holdings
		security_to_holdings_map = {}
		for holding in holdings:
			security = holding.security
			if security not in security_to_holdings_map:
				security_to_holdings_map[security] = []
			security_to_holdings_map[security].append(holding.name)
		
		# Get securities data for batch request
		securities_data = {}
		for security_name in security_to_holdings_map:
			security = frappe.get_doc("CF Security", security_name)
			if security.symbol:
				securities_data[security_name] = {
					"symbol": security.symbol,
					"currency": security.currency
				}
		
		# Extract symbols
		symbols = [data["symbol"] for data in securities_data.values() if data["symbol"]]
		
		if not symbols:
			frappe.msgprint("No valid symbols found in portfolio securities")
			return 0
		
		try:
			updated_count = 0
			total_steps = len(securities_data)
			
			for security_name, data in securities_data.items():
				symbol = data["symbol"]
				security_currency = data["currency"]
	
				frappe.publish_progress(
					percent=(updated_count+1)/total_steps * 100,
					title="Processing",
					description=f"Processing item {updated_count+1} of {total_steps} ({symbol})"
				)
				
				if not symbol:
					updated_count += 1
					continue
				
				try:
					# Get historical data for the start date
					ticker = yf.Ticker(symbol)
					hist = ticker.history(start=start_date_str, end=end_date_str)
					
					if hist.empty:
						frappe.log_error(
							f"No historical data available for {symbol} on {start_date_str}",
							"Portfolio Purchase Price Update Error"
						)
						updated_count += 1
						continue
					
					# Get the closing price from the historical data
					if 'Close' in hist.columns and len(hist) > 0:
						close_price = flt(hist['Close'].iloc[0])
						
						# Update each holding for this security
						for holding_name in security_to_holdings_map[security_name]:
							holding = frappe.get_doc("CF Portfolio Holding", holding_name)
							
							# Set average_purchase_price based on currency conversion if needed
							if security_currency == self.currency:
								# No conversion needed if currencies match
								holding.average_purchase_price = close_price
							else:
								# Convert price to portfolio currency
								try:
									conversion_rate = get_exchange_rate(security_currency, self.currency)
									if security_currency.upper() == 'GBP':
										conversion_rate = conversion_rate / 100
									if conversion_rate:
										holding.average_purchase_price = flt(close_price * conversion_rate)
								except Exception as e:
									frappe.log_error(
										f"Currency conversion failed for {symbol}: {str(e)}",
										"Portfolio Purchase Price Update Error"
									)
									# Use unconverted price if conversion fails
									holding.average_purchase_price = close_price
							
							# Save the holding
							holding.save()
							updated_count += 1
				
				except Exception as e:
					frappe.log_error(
						f"Failed to update {symbol} historical price data: {str(e)}",
						"Portfolio Purchase Price Update Error"
					)
			
			return updated_count
			
		except Exception as e:
			frappe.log_error(
				f"Historical price update failed: {str(e)}",
				"Portfolio Purchase Price Update Error"
			)
			return 0
	
	@frappe.whitelist()
	def calculate_portfolio_performance(self):
		"""Calculate overall portfolio performance metrics"""
		try:
			# Get all holdings for this portfolio
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters={"portfolio": self.name},
				fields=["*"]
			)
			
			if not holdings:
				return {'success': False, 'error': _('No holdings found in this portfolio')}
			
			# Initialize metrics
			total_current_value = 0
			total_cost = 0
			total_dividend_income = 0
			
			# Calculate totals from holdings
			for holding in holdings:
				total_current_value += flt(holding.current_value or 0)
				total_cost += flt(holding.base_cost or 0)
				total_dividend_income += flt(holding.total_dividend_income or 0)
			
			# Set basic portfolio values
			self.cost = total_cost
			self.current_value = total_current_value
			
			# Calculate price-based returns
			price_return = total_current_value - total_cost
			self.returns_price = price_return
			
			# Calculate price-based returns percentage
			if total_cost > 0:
				self.returns_percentage_price = flt((price_return / total_cost) * 100, 2)
			else:
				self.returns_percentage_price = 0
			
			# Use actual total dividend income received since portfolio start
			self.returns_dividends = flt(total_dividend_income, 2)
			
			# Calculate dividend returns percentage
			if total_cost > 0:
				self.returns_percentage_dividends = flt((self.returns_dividends / total_cost) * 100, 2)
			else:
				self.returns_percentage_dividends = 0
			
			# Calculate total returns (price + actual dividends)
			total_return = price_return + self.returns_dividends
			self.returns_total = total_return
			
			# Calculate total returns percentage
			if total_cost > 0:
				self.returns_percentage_total = flt((total_return / total_cost) * 100, 2)
			else:
				self.returns_percentage_total = 0
			
			# Calculate portfolio dividend yield (weighted average)
			portfolio_dividend_yield = 0
			if total_current_value > 0:
				for holding in holdings:
					weight = flt((holding.current_value or 0) / total_current_value, 6)
					portfolio_dividend_yield += weight * flt(holding.dividend_yield or 0, 6)
			
			# Calculate annualized metrics if we have a start date
			if self.start_date:
				days_held = date_diff(frappe.utils.now_datetime().strftime('%Y-%m-%d'), self.start_date)
				
				if days_held > 0:
					years_held = flt(days_held / 365.0, 6)
					
					# Annualized price returns
					price_return_rate = self.returns_percentage_price / 100
					self.annualized_percentage_price = flt(
						(((1 + price_return_rate) ** (365.0 / days_held)) - 1) * 100, 
						2
					)
					
					# Convert annualized percentage to currency amount
					self.annualized_price = flt((total_cost * self.annualized_percentage_price / 100), 2)
					
					# Annualized dividend returns based on actual dividends received
					if years_held > 0:
						annualized_dividend_rate = (self.returns_dividends / total_cost) / years_held if total_cost > 0 else 0
						self.annualized_percentage_dividends = flt(annualized_dividend_rate * 100, 2)
						self.annualized_dividends = flt(total_cost * annualized_dividend_rate, 2)
					else:
						# For very short periods, use current dividend yield
						self.annualized_percentage_dividends = flt(portfolio_dividend_yield, 2)
						self.annualized_dividends = flt(total_current_value * portfolio_dividend_yield / 100, 2)
					
					# Total annualized returns
					self.annualized_percentage_total = flt(self.annualized_percentage_price + self.annualized_percentage_dividends, 2)
					self.annualized_total = flt(self.annualized_price + self.annualized_dividends, 2)
					
				else:
					# If portfolio is brand new (less than a day old)
					self.annualized_percentage_price = self.returns_percentage_price
					self.annualized_price = self.returns_price
					self.annualized_percentage_dividends = flt(portfolio_dividend_yield, 2)
					self.annualized_dividends = flt(total_current_value * portfolio_dividend_yield / 100, 2)
					self.annualized_percentage_total = flt(self.annualized_percentage_price + self.annualized_percentage_dividends, 2)
					self.annualized_total = flt(self.annualized_price + self.annualized_dividends, 2)
			else:
				# If no start date
				self.annualized_percentage_price = self.returns_percentage_price
				self.annualized_price = self.returns_price
				self.annualized_percentage_dividends = flt(portfolio_dividend_yield, 2)
				self.annualized_dividends = flt(total_current_value * portfolio_dividend_yield / 100, 2)
				self.annualized_percentage_total = flt(self.annualized_percentage_price + self.annualized_percentage_dividends, 2)
				self.annualized_total = flt(self.annualized_price + self.annualized_dividends, 2)
	
			self.save()
			
			return {'success': True}
			
		except Exception as e:
			frappe.log_error(f"Error calculating portfolio performance: {str(e)}", 
							"Portfolio Performance Error")
			return {'success': False, 'error': str(e)}

@frappe.whitelist()
def process_portfolio_ai_analysis(portfolio_name, user):
	"""Process AI analysis for the portfolio (meant to be run as a background job)"""
	try:
		# Get the portfolio document
		portfolio = frappe.get_doc("CF Portfolio", portfolio_name)
		
		try:
			from openai import OpenAI            
		except ImportError:
			frappe.log_error("OpenAI package is not installed. Please run 'bench pip install openai'", "AI Analysis Error")
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'message': _('OpenAI package is not installed. Please run "bench pip install openai"')
				},
				user=user
			)
			return False
		
		try:
			# Get OpenWebUI settings
			settings = frappe.get_single("CF Settings")
			client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
			model = settings.default_ai_model
			if not model:
				raise ValueError(_('Default AI model is not configured in CF Settings'))
			
			# Get all holdings for this portfolio
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters=[
					["portfolio", "=", portfolio_name],
				],
				fields=["*"]
			)
			
			if not holdings:
				raise ValueError(_('No holdings found in this portfolio'))
			
			prompt = portfolio.ai_prompt or ""
			
			prompt = re.sub(r'\(\((\w+)\)\)', lambda match: replace_variables(match, portfolio), prompt)
			
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters={"portfolio": portfolio.name},
				fields=["name", "security"]
			)
			
			if holdings:
				# Find all ***HOLDINGS*** sections in the prompt
				holdings_pattern = r'\*\*\*HOLDINGS\*\*\*(.*?)\*\*\*HOLDINGS\*\*\*'
				holdings_matches = re.findall(holdings_pattern, prompt, re.DOTALL)
				
				if holdings_matches:
					# Process each holding separately and create sections for each
					all_holding_sections = []
					
					for holding_info in holdings:
						# Get both holding and security documents
						holding_doc = frappe.get_doc("CF Portfolio Holding", holding_info.name)
						security_doc = frappe.get_doc("CF Security", holding_info.security)
						
						# Process each ***HOLDINGS*** section for this holding
						holding_sections = []
						for holdings_content in holdings_matches:
							holding_prompt = holdings_content
							
							# Replace {{variable}} with security fields
							def replace_security_variables(match):
								variable_name = match.group(1)
								try:
									field_value = getattr(security_doc, variable_name, None)
									return str(field_value) if field_value is not None else ""
								except AttributeError:
									return match.group(0)
							
							# Replace [[variable]] with holding fields
							def replace_holding_variables(match):
								variable_name = match.group(1)
								try:
									field_value = getattr(holding_doc, variable_name, None)
									return str(field_value) if field_value is not None else ""
								except AttributeError:
									return match.group(0)
							
							# Apply security and holding replacements
							holding_prompt = re.sub(r'\{\{([\w\.]+)\}\}', lambda match: replace_variables(match, security_doc), holding_prompt)
							holding_prompt = re.sub(r'\[\[([\w\.]+)\]\]', lambda match: replace_variables(match, holding_doc), holding_prompt)
							
							holding_sections.append(holding_prompt)
						
						# Join sections for this holding
						all_holding_sections.append("***HOLDINGS***" + "***HOLDINGS******HOLDINGS***".join(holding_sections) + "***HOLDINGS***")
					
					# Replace all ***HOLDINGS*** sections in the original prompt with processed content
					# First, get the content before first and after last ***HOLDINGS*** markers
					parts = re.split(r'\*\*\*HOLDINGS\*\*\*.*?\*\*\*HOLDINGS\*\*\*', prompt, flags=re.DOTALL)
					
					# Reconstruct the prompt with all holdings processed
					final_parts = []
					final_parts.append(parts[0])  # Content before first ***HOLDINGS***
					
					for holding_section in all_holding_sections:
						# Remove the ***HOLDINGS*** markers from the processed content
						clean_holding_section = holding_section.replace("***HOLDINGS***", "")
						final_parts.append(clean_holding_section)
					
					if len(parts) > 1:
						final_parts.append(parts[-1])  # Content after last ***HOLDINGS***
					
					prompt = "\n\n".join(final_parts)

			# Make the API call
			messages = [
				{"role": "system", "content": settings.system_content},
				{"role": "user", "content": prompt},
			]
			
			response = client.chat.completions.create(
				model=model,
				messages=messages,
				stream=False,
				temperature=0.2
			)
			
			# Get content from response
			content = response.choices[0].message.content
			
			# Convert to markdown for better display
			markdown_content = safe_markdown_to_html(content)
			
			# Save to portfolio
			portfolio.ai_suggestion = markdown_content
			portfolio.save()
			
			# Create CF Chat and CF Chat Message
			chat_doc = frappe.new_doc("CF Chat")
			chat_doc.portfolio = portfolio_name
			chat_doc.title = f"Portfolio Analysis for {portfolio.portfolio_name} - {frappe.utils.today()}"
			chat_doc.system_prompt = settings.system_content
			chat_doc.save()
			
			# Create the chat message
			message_doc = frappe.new_doc("CF Chat Message")
			message_doc.chat = chat_doc.name
			message_doc.prompt = prompt
			message_doc.response = content
			message_doc.response_html = markdown_content
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
					'portfolio_id': portfolio_name,
					'status': 'success',
					'chat_id': chat_doc.name,
					'message': _(f"Portfolio '{portfolio_name}' AI analysis has been successfully generated and saved.")
				},
				user=user
			)
			
			return True
			
		except requests.exceptions.RequestException as e:
			error_message = f"Request error: {str(e)}"
			frappe.log_error(error_message, "OpenWebUI API Error")
			
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'error': error_message,
					'message': error_message
				},
				user=user
			)
			
			return False
			
		except Exception as e:
			error_message = f"Error generating AI analysis: {str(e)}"
			frappe.log_error(error_message, "AI Analysis Error")
			
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'error': error_message,
					'message': _(f"Error generating AI analysis for portfolio '{portfolio_name}': {error_message}")
				},
				user=user
			)
			
			return False
	
	except Exception as e:
		error_msg = str(e)
		frappe.log_error(
			f"Error generating AI analysis for portfolio {portfolio_name}: {error_msg}",
			"Portfolio AI Analysis Error"
		)
		
		# Notify user of failure
		frappe.publish_realtime(
			event='cf_job_completed',
			message={
				'portfolio_id': portfolio_name,
				'status': 'error',
				'error': error_msg,
				'message': _(f"Error generating AI analysis for portfolio '{portfolio_name}': {error_msg}")
			},
			user=user
		)
		
		return False


def process_evaluate_holdings_news(portfolio_name, user):
	"""Process news evaluation for all holdings in the portfolio (meant to be run as a background job)"""
	
	try:
		try:
			from openai import OpenAI            
		except ImportError:
			frappe.log_error("OpenAI package is not installed. Please run 'bench pip install openai'", "AI Analysis Error")
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'message': _('OpenAI package is not installed. Please run "bench pip install openai"')
				},
				user=user
			)
			return False
		
		try:
			# Get OpenWebUI settings
			settings = frappe.get_single("CF Settings")
			client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
			model = settings.default_ai_model
			if not model:
				raise ValueError(_('Default AI model is not configured in CF Settings'))
			
			# Get all holdings for this portfolio
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters=[
					[
						"portfolio", "=", portfolio_name
					],
				],
				fields=["name", "security"]
			)
			
			if not holdings:
				raise ValueError(_('No holdings found in this portfolio'))
			
			# Filter securities that have news and need evaluation
			securities_to_evaluate = []
			for holding_info in holdings:
				security_doc = frappe.get_doc("CF Security", holding_info.security)
				
				# Check if security has news in the JSON field
				if not security_doc.news or security_doc.need_evaluation:
					continue  # Skip if no news
				
				# Parse the news JSON data
				try:
					news_data = frappe.parse_json(security_doc.news) if isinstance(security_doc.news, str) else security_doc.news
				except (ValueError, TypeError):
					continue  # Skip if news JSON is invalid
				
				if not isinstance(news_data, list) or not news_data:
					continue  # Skip if no news items
				
				# Check if there's news newer than ai_modified
				recent_news_items = []
				if security_doc.ai_modified:
					# Filter news items that are newer than ai_modified
					for news_item in news_data:
						if isinstance(news_item, dict) and 'content' in news_item:
							content = news_item['content']
							if 'pubDate' in content:
								pub_date = date_parser.parse(content['pubDate'])
								
								# Ensure both datetimes are offset-aware
								if security_doc.ai_modified.tzinfo is None:
									security_doc.ai_modified = security_doc.ai_modified.replace(tzinfo=timezone.utc)
								
								if pub_date > security_doc.ai_modified:
									recent_news_items.append(news_item)
					
					if not recent_news_items:
						continue  # Skip if no recent news
					news_items_to_process = recent_news_items
				else:
					# If no ai_modified date, process all news
					news_items_to_process = news_data
				
				# Prepare headlines for this security
				headlines = []
				for news_item in news_items_to_process:
					if isinstance(news_item, dict) and 'content' in news_item:
						content = news_item['content']
						if 'title' in content and content['title']:
							headlines.append(content['title'])
				
				if headlines:
					securities_to_evaluate.append({
						'security_doc': security_doc,
						'headlines': headlines
					})
			
			if not securities_to_evaluate:
				# Notify user that no securities need evaluation
				frappe.publish_realtime(
					event='cf_job_completed',
					message={
						'portfolio_id': portfolio_name,
						'status': 'success',
						'message': _(f"No securities in portfolio '{portfolio_name}' require news evaluation.")
					},
					user=user
				)
				return True
			
			# Build the prompt with actual security data
			prompt = """I own the following stocks **that I previously evaluated based on fundamentals**.  
Analyze their recent headlines **only for material changes** that could alter their valuation.  

### **Strict Evaluation Criteria**  
Flag for re-evaluation **ONLY** if any of these occur:  
1. **Earnings/Guidance Shifts**:  
   - EPS/revenue miss/beat >5% vs. estimates.  
   - FY guidance raised/lowered significantly.  
2. **Business Risks/Opportunities**:  
   - M&A, major partnerships, or divestitures.  
   - Product launches with >10% revenue impact.  
3. **Financial Health Changes**:  
   - New debt/equity issuance or credit downgrades.  
   - Cash flow warnings or liquidity risks.  
4. **Management/Legal Risks**:  
   - CEO/CFO departure or fraud allegations.  
   - Major lawsuits/regulatory actions.

**Response Format (Strict JSON):**
[
	{
		"Company": "Company name",
		"Symbol": "ticker symbol",
		"Evaluate": "Yes/No",
		"Reasoning": "Explain why need re-evaluation"
	}
]

"""
			
			# Add each security's information to the prompt
			for item in securities_to_evaluate:
				security_doc = item['security_doc']
				headlines = item['headlines']
				
				prompt += f"*Company*: {security_doc.security_name or ''}\n"
				prompt += f"*Symbol*: {security_doc.symbol or ''}\n"
				prompt += "*Headlines*:\n"
				for headline in headlines:
					prompt += f"- {headline}\n"
				prompt += "\n"

			# Make the API call
			messages = [
				{"role": "system", "content": settings.system_content},
				{"role": "user", "content": prompt},
			]
			
			response = client.chat.completions.create(
				model=model,
				messages=messages,
				stream=False,
				temperature=0.2
			)
			
			# Get content from response
			content = response.choices[0].message.content
			
			# Convert to markdown for better display
			content = clear_string(content)
			json_content = frappe.parse_json(content)

			# Validate the JSON structure
			if not isinstance(json_content, list):
				raise ValueError("AI response is not a valid JSON array")

			for item in json_content:
				if not isinstance(item, dict):
					raise ValueError("AI response item is not a valid JSON object")
				
				# Ensure required fields are present
				if 'Company' not in item or 'Symbol' not in item or 'Evaluate' not in item or 'Reasoning' not in item:
					raise ValueError("AI response item is missing required fields")
				
				# Find the security document from our evaluated securities list by symbol
				if item['Evaluate'].lower() == 'yes':
					security_found = None
					for eval_item in securities_to_evaluate:
						if eval_item['security_doc'].symbol == item['Symbol']:
							security_found = eval_item['security_doc']
							break
					
					if security_found:
						# Convert datetime to MySQL compatible format
						current_time = frappe.utils.now_datetime()
						security_found.need_evaluation = True
						security_found.news_reasoning = item['Reasoning']
						security_found.ai_modified = current_time.strftime('%Y-%m-%d %H:%M:%S')
						try:
							security_found.save()
						except Exception as save_err:
							# Use shorter error message
							err_msg = f"Save failed for {item['Symbol']}: {str(save_err)[:50]}..."
							frappe.log_error(message=err_msg, title="Security Save Error")
					else:
						# Use shorter error message
						err_msg = f"Symbol not found: {item['Symbol']}"
						frappe.log_error(message=err_msg, title="Security Not Found")

			frappe.db.commit()  # Single commit for all changes
			
			# Notify the user that the analysis is complete
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'success',
					'message': _(f"Portfolio '{portfolio_name}' AI news evaluation has been successfully completed.")
				},
				user=user
			)
			
			return True
			
		except requests.exceptions.RequestException as e:
			error_msg = f"API Error: {str(e)[:50]}..."
			frappe.log_error(message=error_msg, title="API Error")
			
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'error': error_msg,
					'message': error_msg
				},
				user=user
			)
			
			return False
			
		except Exception as e:
			error_msg = f"Analysis Error: {str(e)[:50]}..."
			frappe.log_error(message=error_msg, title="News Analysis Error")
			
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'error': error_msg,
					'message': error_msg
				},
				user=user
			)
			
			return False
	
	except Exception as e:
		error_msg = str(e)
		frappe.log_error(
			f"Error generating AI news evaluation for portfolio {portfolio_name}: {error_msg}",
			"Portfolio AI Analysis Error"
		)
		
		# Notify user of failure
		frappe.publish_realtime(
			event='cf_job_completed',
			message={
				'portfolio_id': portfolio_name,
				'status': 'error',
				'error': error_msg,
				'message': _(f"Error generating AI news evaluation for portfolio '{portfolio_name}': {error_msg}")
			},
			user=user
		)
		
		return False
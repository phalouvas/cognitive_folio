import frappe
from frappe.model.document import Document
from frappe.utils import flt, add_days, date_diff
from datetime import datetime, timedelta
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from cognitive_folio.utils.markdown import safe_markdown_to_html

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
	def generate_holdings_ai_suggestions(self):
		"""Queue AI suggestion generation for each holding as separate background jobs"""
		from frappe.utils.background_jobs import enqueue

		try:
			# Get holdings in this portfolio
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters=[
					["portfolio", "=", self.name],
					["security_type", "!=", "Cash"]
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
				job_name=job_name,
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
		
		# Get all holdings for this portfolio (excluding Cash type securities)
		holdings = frappe.get_all(
			"CF Portfolio Holding",
			filters=[
				["portfolio", "=", self.name],
				["security_type", "!=", "Cash"]
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
		# Log start of process
		frappe.logger().info(f"Starting AI analysis generation for portfolio {portfolio_name}")
		
		# Get the portfolio document
		portfolio = frappe.get_doc("CF Portfolio", portfolio_name)
		
		try:
			from openai import OpenAI            
		except ImportError:
			frappe.log_error("OpenAI package is not installed. Please run 'bench pip install openai'", "AI Analysis Error")
			# Notify user of failure
			frappe.publish_realtime(
				event='portfolio_ai_analysis_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'error': 'OpenAI package is not installed'
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
			
			# Calculate total portfolio value and other metrics
			total_value = sum(holding.current_value for holding in holdings if holding.current_value)
			total_profit_loss = sum(holding.profit_loss for holding in holdings if holding.profit_loss)
			
			# Group holdings by various categories for analysis
			sector_allocation = {}
			industry_allocation = {}
			country_allocation = {}
			region_allocation = {}
			subregion_allocation = {}
			security_type_allocation = {}
			
			for holding in holdings:
				# Sector allocation
				if holding.sector:
					if holding.sector not in sector_allocation:
						sector_allocation[holding.sector] = 0
					sector_allocation[holding.sector] += holding.current_value or 0
				
				# Industry allocation
				if holding.industry:
					if holding.industry not in industry_allocation:
						industry_allocation[holding.industry] = 0
					industry_allocation[holding.industry] += holding.current_value or 0
				
				# Country allocation
				if holding.country:
					if holding.country not in country_allocation:
						country_allocation[holding.country] = 0
					country_allocation[holding.country] += holding.current_value or 0
				
				# Region allocation
				if holding.region:
					if holding.region not in region_allocation:
						region_allocation[holding.region] = 0
					region_allocation[holding.region] += holding.current_value or 0
				
				# Subregion allocation
				if holding.subregion:
					if holding.subregion not in subregion_allocation:
						subregion_allocation[holding.subregion] = 0
					subregion_allocation[holding.subregion] += holding.current_value or 0
				
				# Security type allocation
				if holding.security_type:
					if holding.security_type not in security_type_allocation:
						security_type_allocation[holding.security_type] = 0
					security_type_allocation[holding.security_type] += holding.current_value or 0
			
			# Convert raw values to percentages
			if total_value > 0:
				sector_allocation = {k: (v/total_value*100) for k, v in sector_allocation.items()}
				industry_allocation = {k: (v/total_value*100) for k, v in industry_allocation.items()}
				country_allocation = {k: (v/total_value*100) for k, v in country_allocation.items()}
				region_allocation = {k: (v/total_value*100) for k, v in region_allocation.items()}
				subregion_allocation = {k: (v/total_value*100) for k, v in subregion_allocation.items()}
				security_type_allocation = {k: (v/total_value*100) for k, v in security_type_allocation.items()}
			
			# Get target allocations from CF Asset Allocation
			target_allocations = frappe.get_all(
				"CF Asset Allocation",
				filters={"portfolio": portfolio_name},
				fields=["allocation_type", "asset_class", "target_percentage", "current_percentage", "difference"]
			)
			
			# Group target allocations by type
			grouped_targets = {}
			for alloc in target_allocations:
				alloc_type = alloc.allocation_type
				if alloc_type not in grouped_targets:
					grouped_targets[alloc_type] = []
				grouped_targets[alloc_type].append(alloc)
			
			# Build the prompt with portfolio data
			prompt = f"""
			Portfolio Name: {portfolio.portfolio_name}
			Risk Profile: {portfolio.risk_profile or "Not specified"}
			Currency: {portfolio.currency or "Not specified"}
			Total Value: {total_value} {portfolio.currency}
			Total Profit/Loss: {total_profit_loss} {portfolio.currency} ({(total_profit_loss/total_value*100) if total_value else 0:.2f}%)
			
			Holdings:
			"""
			
			# Add holdings data
			for holding in holdings:
				prompt += f"""
				- {holding.security_name or holding.security} ({holding.security_type or "Unknown type"})
				  Quantity: {holding.quantity}
				  Current Value: {holding.current_value} {portfolio.currency} ({holding.allocation_percentage or 0:.2f}% of portfolio)
				  Profit/Loss: {holding.profit_loss or 0} {portfolio.currency} ({holding.profit_loss_percentage or 0:.2f}%)
				  Sector: {holding.sector or "Unknown"}
				  Industry: {holding.industry or "Unknown"}
				  Country: {holding.country or "Unknown"}
				  Region: {holding.region or "Unknown"}
				  Subregion: {holding.subregion or "Unknown"}
				"""
			
			# Add current allocation data
			prompt += "\nSector Allocation:\n"
			for sector, percentage in sorted(sector_allocation.items(), key=lambda x: x[1], reverse=True):
				prompt += f"- {sector}: {percentage:.2f}%\n"
			
			prompt += "\nIndustry Allocation:\n"
			for industry, percentage in sorted(industry_allocation.items(), key=lambda x: x[1], reverse=True):
				prompt += f"- {industry}: {percentage:.2f}%\n"
			
			prompt += "\nCountry Allocation:\n"
			for country, percentage in sorted(country_allocation.items(), key=lambda x: x[1], reverse=True):
				prompt += f"- {country}: {percentage:.2f}%\n"
			
			prompt += "\nRegion Allocation:\n"
			for region, percentage in sorted(region_allocation.items(), key=lambda x: x[1], reverse=True):
				prompt += f"- {region}: {percentage:.2f}%\n"
			
			prompt += "\nSubregion Allocation:\n"
			for subregion, percentage in sorted(subregion_allocation.items(), key=lambda x: x[1], reverse=True):
				prompt += f"- {subregion}: {percentage:.2f}%\n"
			
			prompt += "\nSecurity Type Allocation:\n"
			for security_type, percentage in sorted(security_type_allocation.items(), key=lambda x: x[1], reverse=True):
				prompt += f"- {security_type}: {percentage:.2f}%\n"

			prompt += settings.user_content

			# Check if Target Allocations placeholder exists in user_content
			target_allocations_text = ""
			if grouped_targets:
				target_allocations_text = "\nTarget Allocations:\n"
				for alloc_type, allocations in grouped_targets.items():
					target_allocations_text += f"\n{alloc_type} Targets:\n"
					for alloc in sorted(allocations, key=lambda x: x.target_percentage, reverse=True):
						current = alloc.current_percentage or 0
						target = alloc.target_percentage or 0
						diff = alloc.difference or 0
						target_allocations_text += f"- {alloc.asset_class}: Current {current:.2f}% vs Target {target:.2f}% (Difference: {diff:.2f}%)\n"
			
			# Replace {Target Allocations} placeholder in prompt if it exists
			if "{Target Allocations}" in prompt:
				prompt = prompt.replace("{Target Allocations}", target_allocations_text)

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
			portfolio.ai_prompt = prompt
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
				event='portfolio_ai_analysis_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'success',
					'chat_id': chat_doc.name
				},
				user=user
			)
			
			# Also send a notification sound and alert similar to chat messages
			frappe.publish_realtime(
				event='eval_js',
				message='frappe.show_alert({message: "Portfolio AI analysis completed successfully", indicator: "green"}); try { const audio = new Audio("/assets/cognitive_folio/sounds/notification.mp3"); audio.volume = 0.5; audio.play(); } catch(e) { console.log("Audio play failed:", e); }',
				user=user
			)
			
			frappe.logger().info(f"Successfully generated AI analysis for portfolio {portfolio_name}")
			
			return True
			
		except requests.exceptions.RequestException as e:
			error_message = f"Request error: {str(e)}"
			frappe.log_error(error_message, "OpenWebUI API Error")
			
			# Notify user of failure
			frappe.publish_realtime(
				event='portfolio_ai_analysis_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'error': error_message
				},
				user=user
			)
			
			# Also send error notification
			frappe.publish_realtime(
				event='eval_js',
				message='frappe.show_alert({message: "Portfolio AI analysis failed. Please check the logs.", indicator: "red"});',
				user=user
			)
			
			return False
			
		except Exception as e:
			error_message = f"Error generating AI analysis: {str(e)}"
			frappe.log_error(error_message, "AI Analysis Error")
			
			# Notify user of failure
			frappe.publish_realtime(
				event='portfolio_ai_analysis_completed',
				message={
					'portfolio_id': portfolio_name,
					'status': 'error',
					'error': error_message
				},
				user=user
			)
			
			# Also send error notification
			frappe.publish_realtime(
				event='eval_js',
				message='frappe.show_alert({message: "Portfolio AI analysis failed. Please check the logs.", indicator: "red"});',
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
			event='portfolio_ai_analysis_completed',
			message={
				'portfolio_id': portfolio_name,
				'status': 'error',
				'error': error_msg
			},
			user=user
		)
		
		# Also send error notification
		frappe.publish_realtime(
			event='eval_js',
			message='frappe.show_alert({message: "Portfolio AI analysis failed. Please check the logs.", indicator: "red"});',
			user=user
		)
		
		return False

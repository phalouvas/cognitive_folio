import frappe
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from datetime import datetime, timedelta
from openai import OpenAI

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
		"""Generate AI suggestions for all holdings in this portfolio"""
		try:
			# Calculate the timestamp for 24 hours ago as a datetime object
			cutoff_time = datetime.now() - timedelta(hours=24)
			
			# Get holdings in this portfolio
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters=[
					["portfolio", "=", self.name],
					["security_type", "!=", "Cash"]
				],
				fields=["name", "security"]
			)
			
			if not holdings:
				return {'success': False, 'error': _('No non-cash holdings found in this portfolio')}
			
			total_count = len(holdings)
			
			for i, holding in enumerate(holdings):
				frappe.publish_progress(
					percent=(i)/total_count * 100,
					title=_("Generating AI Suggestions"),
					description=_("Processing holding {0} of {1}").format(i+1, total_count)
				)
				
				if not holding.security:
					continue
					
				try:
					# Get the security document
					security = frappe.get_doc("CF Security", holding.security)

					# Now properly compare datetime objects
					if not security.ai_suggestion or security.modified < cutoff_time:
						security.generate_ai_suggestion()
									
				except Exception as e:
					frappe.log_error(
						f"Error generating AI suggestion for holding {holding.name}: {str(e)}",
						"Portfolio Holding AI Generation Error"
					)
					continue
			
			frappe.publish_progress(
				percent=100,
				title=_("Generating AI Suggestions"),
				description=_("Processing complete")
			)
			
			return {'success': True, 'count': total_count}
			
		except Exception as e:
			frappe.log_error(f"Error generating AI suggestions for holdings: {str(e)}", "Portfolio Error")
			return {'success': False, 'error': str(e)}

	@frappe.whitelist()
	def fetch_all_prices(self):
		"""Update prices for all holdings in this portfolio using batch requests"""
		try:
			import yfinance as yf
		except ImportError:
			frappe.msgprint("YFinance package is not installed. Please run 'bench pip install yfinance'")
			return 0
		
		# Calculate the timestamp for 24 hours ago as a datetime object
		cutoff_time = datetime.now() - timedelta(hours=24)
		
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
					"currency": security.currency,
					"doc": security,
					"datetime": security.modified
				}
		
		# Extract symbols for batch request
		symbols = [data["symbol"] for data in securities_data.values() if data["symbol"]]
		
		if not symbols:
			frappe.msgprint("No valid symbols found in portfolio securities")
			return 0
		
		try:
			# Make a single batch request for all symbols
			tickers = yf.Tickers(" ".join(symbols))
			
			# Update each holding with the batch data
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
				
				if not symbol or symbol not in tickers.tickers or security.modified > cutoff_time:
					updated_count += 1
					continue
					
				ticker = tickers.tickers[symbol]
				
				try:
					# Get ticker info
					ticker_info = ticker.info
					
					# Update current price for all holdings of this security
					if 'regularMarketPrice' in ticker_info:
						price_in_security_currency = flt(ticker_info['regularMarketPrice'])
						
						# Update each holding for this security
						for holding_name in security_to_holdings_map[security_name]:
							holding = frappe.get_doc("CF Portfolio Holding", holding_name)
							
							# Set current_price based on currency conversion if needed
							if security_currency == self.currency:
								# No conversion needed if currencies match
								holding.current_price = price_in_security_currency
							else:
								# Convert price to portfolio currency
								try:
									conversion_rate = get_exchange_rate(security_currency, self.currency)
									if conversion_rate:
										holding.current_price = flt(price_in_security_currency * conversion_rate)
								except Exception as e:
									frappe.log_error(
										f"Currency conversion failed for {symbol}: {str(e)}",
										"Portfolio Currency Conversion Error"
									)
									# Use unconverted price if conversion fails
									holding.current_price = price_in_security_currency
							
							# Update other values in the holding
							holding.current_value = holding.quantity * holding.current_price
							if holding.average_purchase_price and holding.quantity:
								total_cost = holding.average_purchase_price * holding.quantity
								holding.profit_loss = holding.current_value - total_cost
							
							# Save the holding
							holding.save()
							updated_count += 1
					
					# Save ticker info in the security document if needed
					if ticker_info and hasattr(data["doc"], "ticker_info"):
						security_doc = data["doc"]
						security_doc.ticker_info = frappe.as_json(ticker_info)
						security_doc.current_price = ticker_info['regularMarketPrice']
						
						# Update sector and industry if they exist in the security doctype
						if hasattr(security_doc, "sector") and 'sector' in ticker_info:
							security_doc.sector = ticker_info['sector']
						
						if hasattr(security_doc, "industry") and 'industry' in ticker_info:
							security_doc.industry = ticker_info['industry']
						
						security_doc.save()
						
				except Exception as e:
					frappe.log_error(
						f"Failed to update {symbol} from batch data: {str(e)}",
						"Portfolio Batch Update Error"
					)
			
			return updated_count
			
		except Exception as e:
			frappe.log_error(
				f"Batch update failed: {str(e)}",
				"Portfolio Batch Update Error"
			)
			return 0
	
	@frappe.whitelist()
	def generate_portfolio_ai_analysis(self):
		"""Generate AI analysis for the entire portfolio"""
		try:
			# Get OpenWebUI settings
			settings = frappe.get_single("CF Settings")
			client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
			model = settings.default_ai_model
			if not model:
				frappe.throw(_('Default AI model is not configured in CF Settings'))
	
			# Get all holdings for this portfolio
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters=[
					["portfolio", "=", self.name],
				],
				fields=["name", "security", "security_name", "quantity", "current_price", 
						"current_value", "allocation_percentage", "security_type",
						"sector", "industry", "country", "profit_loss", "profit_loss_percentage"]
			)
			
			if not holdings:
				return {'success': False, 'error': _('No holdings found in this portfolio')}
			
			# Calculate total portfolio value and other metrics
			total_value = sum(holding.current_value for holding in holdings if holding.current_value)
			total_profit_loss = sum(holding.profit_loss for holding in holdings if holding.profit_loss)
			
			# Group holdings by various categories for analysis
			sector_allocation = {}
			industry_allocation = {}
			country_allocation = {}
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
				security_type_allocation = {k: (v/total_value*100) for k, v in security_type_allocation.items()}
			
			# Get target allocations from CF Asset Allocation
			target_allocations = frappe.get_all(
				"CF Asset Allocation",
				filters={"portfolio": self.name},
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
			Analyze this portfolio:
			
			Portfolio Name: {self.portfolio_name}
			Risk Profile: {self.risk_profile or "Not specified"}
			Total Value: {total_value} {self.currency}
			Total Profit/Loss: {total_profit_loss} {self.currency} ({(total_profit_loss/total_value*100) if total_value else 0:.2f}%)
			
			Holdings:
			"""
			
			# Add holdings data
			for holding in holdings:
				prompt += f"""
				- {holding.security_name or holding.security} ({holding.security_type or "Unknown type"})
				  Quantity: {holding.quantity}
				  Current Value: {holding.current_value} {self.currency} ({holding.allocation_percentage or 0:.2f}% of portfolio)
				  Profit/Loss: {holding.profit_loss or 0} {self.currency} ({holding.profit_loss_percentage or 0:.2f}%)
				  Sector: {holding.sector or "Unknown"}
				  Industry: {holding.industry or "Unknown"}
				  Country: {holding.country or "Unknown"}
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
			
			prompt += "\nSecurity Type Allocation:\n"
			for security_type, percentage in sorted(security_type_allocation.items(), key=lambda x: x[1], reverse=True):
				prompt += f"- {security_type}: {percentage:.2f}%\n"
			
			# Add target allocation data
			if grouped_targets:
				prompt += "\nTarget Allocations:\n"
				for alloc_type, allocations in grouped_targets.items():
					prompt += f"\n{alloc_type} Targets:\n"
					for alloc in sorted(allocations, key=lambda x: x.target_percentage, reverse=True):
						current = alloc.current_percentage or 0
						target = alloc.target_percentage or 0
						diff = alloc.difference or 0
						prompt += f"- {alloc.asset_class}: Current {current:.2f}% vs Target {target:.2f}% (Difference: {diff:.2f}%)\n"
			
			# Add final instructions
			prompt += """
			Please provide a comprehensive analysis of this portfolio including:
			
			1. Overall assessment of portfolio composition and diversification
			2. Risk analysis based on allocations and holdings
			3. Recommendations for rebalancing or adjustments to align with target allocations
			4. Potential concerns or areas of strength
			5. Specific actions to take to bring the portfolio closer to target allocations

			Do not use your own name "Warren Buffet" in the response.
			Also do not include any tables, instead make bulleted lists.
			"""
			
			# Make the API call
			messages = [
				{"role": "system", "content": "You are Warren Buffet, the legendary investor providing analysis and recommendations."},
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
			
			# Save to ai_suggestion field
			self.ai_suggestion = content
			self.save()
			
			return {'success': True}
		
		except Exception as e:
			frappe.log_error(f"Error generating portfolio AI analysis: {str(e)}", "Portfolio AI Analysis Error")
			return {'success': False, 'error': str(e)}
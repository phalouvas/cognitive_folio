# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import json
import requests
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

try:
	import yfinance as yf
	YFINANCE_INSTALLED = True
except ImportError:
	YFINANCE_INSTALLED = False

class CFSecurity(Document):
	def validate(self):
		if self.security_type == "Cash":
			self.symbol = self.security_name
			self.current_price = 1.0

		self.validate_isin()
		self.calculate_fair_value()
		self.calculate_intrinsic_value()
		self.set_alert()
	
	def validate_isin(self):
		"""Validate ISIN format if provided"""
		if self.isin:
			# ISIN is a 12-character alphanumeric code
			if len(self.isin) != 12:
				frappe.throw("ISIN must be 12 characters long")
			
			# Basic format validation: 2 letters country code + 9 alphanumeric + 1 check digit
			if not (self.isin[:2].isalpha() and self.isin[2:11].isalnum() and self.isin[11].isalnum()):
				frappe.throw("ISIN format is invalid. It should be 2 letters country code followed by 9 alphanumeric characters and 1 check digit")

	def after_insert(self):
		"""Fetch and set the current price after inserting the document"""
		if YFINANCE_INSTALLED:
			self.fetch_fundamentals()

	@frappe.whitelist()
	def fetch_current_price(self):
		if self.security_type == "Cash":
			return {'success': False, 'error': _('Price is only for non-cash securities')}
		
		"""Fetch the current price from Yahoo Finance"""
		try:
			ticker = yf.Ticker(self.symbol)
			
			# Using fast_info which is more efficient for basic price data
			self.current_price = ticker.fast_info['last_price']
			self.currency = ticker.fast_info['currency']
			self.save()
			# Get all portfolio holdings of this security
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters={"security": self.name},
				fields=["name"]
			)
			
			# Update each holding with the new price
			for holding in holdings:
				portfolio_holding = frappe.get_doc("CF Portfolio Holding", holding.name)
				portfolio_holding.save()
			return {'success': True, 'price': self.current_price, 'currency': self.currency}
		except Exception as e:
			frappe.log_error(f"Error fetching current price: {str(e)}", "Fetch Current Price Error")
			frappe.throw("Error fetching current price. Please check the symbol.")

	@frappe.whitelist()
	def fetch_fundamentals(self):
		if self.security_type == "Cash":
			return {'success': False, 'error': _('Price is only for non-cash securities')}
		
		"""Fetch the current price from Yahoo Finance"""
		try:
			ticker = yf.Ticker(self.symbol)
			ticker_info = ticker.get_info()
			self.profit_loss = ticker.financials.to_json(date_format='iso')
			self.balance_sheet = ticker.balance_sheet.to_json(date_format='iso')
			self.cash_flow = ticker.cashflow.to_json(date_format='iso')
			self.ticker_info = frappe.as_json(ticker_info)
			self.currency = ticker_info['currency']
			self.current_price = ticker_info['regularMarketPrice']
			self.news = frappe.as_json(ticker.get_news())
			self.country = ticker_info.get('country', '')
			self.dividends = ticker.dividends.to_json(date_format='iso')
			if self.country == "South Korea":
				self.country = "Korea, Republic of"
			if not self.region:
				self.region, self.subregion = get_country_region_from_api(self.country)
			self.save()

			# Get all portfolio holdings of this security
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters={"security": self.name},
				fields=["name"]
			)
			
			# Update each holding with the new price
			for holding in holdings:
				portfolio_holding = frappe.get_doc("CF Portfolio Holding", holding.name)
				portfolio_holding.save()
				
		except Exception as e:
			frappe.log_error(f"Error fetching current price: {str(e)}", "Fetch Current Price Error")
			frappe.throw("Error fetching current price. Please check the symbol.")
	
	@frappe.whitelist()
	def generate_ai_suggestion(self):
		if self.security_type == "Cash":
			return {'success': False, 'error': _('AI suggestion is only for non-cash securities')}
		
		try:
			from openai import OpenAI			
		except ImportError:
			frappe.msgprint("OpenAI package is not installed. Please run 'bench pip install openai'")
			return 0
		
		try:
			# Get OpenWebUI settings
			settings = frappe.get_single("CF Settings")
			client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
			model = settings.default_ai_model
			if not model:
				frappe.throw(_('Default AI model is not configured in CF Settings'))

			news_json = json.loads(self.news) if self.news else []
			# Extract URLs from news data and format with # prefix
			news_urls = ["#" + item.get("content", {}).get("clickThroughUrl", {}).get("url", "") 
							for item in news_json if item.get("content") and item.get("content").get("clickThroughUrl")]
			news = "\n".join(news_urls)
			
			# Create base prompt with security data
			prompt = f"""
			You own stocks of below company and you must decide whether you will buy more, hold, or sell.
			
			Profit and Loss Statement:
			{self.profit_loss}

			Balance Sheet:
			{self.balance_sheet}

			Cash Flow Statement:
			{self.cash_flow}	

			"""                        
			
			# Add final instructions to the prompt
			prompt += """
			Include a rating from 1 to 5, where 1 is the worst and 5 is the best.
			State your recommendation Buy, Hold, or Sell.
			State the price target that you would think for buying and selling.
			Output in JSON format but give titles to each column so I am able to render them in markdown format.
			
			EXAMPLE JSON OUTPUT:
			{
				"Summary": "Your summary here in markdown format",
				"Analysis": "Your evaluation analysis here in markdown format",
				"Risks": "The identified risks here in markdown format",
				"Evaluation": {
					"Rating": 4,
					"Recommendation": "Buy",
					"Price Target Buy Below": 156.01,
					"Price Target Sell Above": 185.18
				}
			}
			"""
			
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

			 # Parse the JSON from the content string, removing any Markdown formatting
			content_string = response.choices[0].message.content
			# Remove Markdown code blocks if present
			if content_string.startswith('```') and '```' in content_string[3:]:
				# Extract content between the first and last backtick markers
				content_string = content_string.split('```', 2)[1]
				# Remove the language identifier if present (e.g., 'json\n')
				if '\n' in content_string:
					content_string = content_string.split('\n', 1)[1]
				# Remove trailing backticks if any remain
				if '```' in content_string:
					content_string = content_string.split('```')[0]
			suggestion = json.loads(content_string)

			# Convert JSON to markdown for better display
			markdown_content = self.convert_json_to_markdown(suggestion)
			
			self.ai_response = content_string
			self.suggestion_action = suggestion.get("Evaluation", {}).get("Recommendation", "")
			self.suggestion_rating = suggestion.get("Evaluation", {}).get("Rating", 0)
			self.suggestion_buy_price = suggestion.get("Evaluation", {}).get("Price Target Buy Below", 0)
			self.suggestion_sell_price = suggestion.get("Evaluation", {}).get("Price Target Sell Above", 0)
			self.ai_suggestion = markdown_content
			self.ai_prompt = prompt
			self.save()
			return {'success': True}
		except requests.exceptions.RequestException as e:
			frappe.log_error(f"Request error: {str(e)}", "OpenWebUI API Error")
			return {'success': False, 'error': str(e)}
		except Exception as e:
			frappe.log_error(f"Error generating AI suggestion: {str(e)}", "AI Suggestion Error")
			return {'success': False, 'error': str(e)}
			
	def convert_json_to_markdown(self, data):
		"""Convert JSON data to markdown format for better display"""
		markdown = []
		
		# Add Summary
		if "Summary" in data:
			markdown.append(f"## Summary\n{data['Summary']}\n")
		
		# Add Evaluation as bullet points
		if "Evaluation" in data:
			eval_data = data["Evaluation"]
			markdown.append("## Evaluation")
			
			rating = "⭐" * int(eval_data.get("Rating", 0))
			markdown.append(f"- Rating: {rating}")
			markdown.append(f"- Recommendation: **{eval_data.get('Recommendation', '-')}**")
			markdown.append(f"- Buy Below: **{self.currency} {eval_data.get('Price Target Buy Below', '-')}**")
			markdown.append(f"- Sell Above: **{self.currency} {eval_data.get('Price Target Sell Above', '-')}**")
			markdown.append("")
		
		# Add Analysis
		if "Analysis" in data:
			markdown.append(f"## Analysis\n{data['Analysis']}\n")

		# Add Risks
		if "Risks" in data:
			markdown.append(f"## Risks\n{data['Risks']}\n")

		return "\n".join(markdown)

	def set_alert(self):
		"""Set an alert for the security"""
		self.is_alert = 0
		self.alert_details = ""

		if self.current_price < self.suggestion_buy_price:
			self.alert_details = f"Current price is below **BUY** price target of {self.suggestion_buy_price}."
			self.is_alert = 1
		if self.current_price > self.suggestion_sell_price:
			self.alert_details = f"Current price is above **SELL** price target of {self.suggestion_sell_price}."
			self.is_alert = 1

	def calculate_intrinsic_value(self):
		"""Calculate intrinsic value using multiple valuation methods"""
		"""The true, fundamental worth of a stock based on its underlying business performance, cash flows, and assets."""
		if self.security_type == "Cash":
			self.intrinsic_value = 1.0
			return
		
		try:
			valuations = {}
			
			# Method 1: Discounted Cash Flow (DCF)
			dcf_value = self._calculate_dcf_value()
			if dcf_value:
				valuations['DCF'] = dcf_value
			
			# Method 2: Dividend Discount Model (DDM)
			ddm_value = self._calculate_ddm_value()
			if ddm_value:
				valuations['DDM'] = ddm_value
			
			# Method 3: Earnings-Based Valuation (P/E)
			pe_value = self._calculate_pe_value()
			if pe_value:
				valuations['P/E'] = pe_value
			
			# Method 4: Book Value / Asset-Based
			book_value = self._calculate_book_value()
			if book_value:
				valuations['Book'] = book_value
			
			# Method 5: Graham Formula
			graham_value = self._calculate_graham_formula()
			if graham_value:
				valuations['Graham'] = graham_value
			
			# Method 6: Residual Income Model
			residual_value = self._calculate_residual_income()
			if residual_value:
				valuations['Residual'] = residual_value
			
			# Calculate weighted average (DCF gets highest weight)
			if valuations:
				weights = {'DCF': 0.3, 'DDM': 0.2, 'P/E': 0.2, 'Book': 0.1, 'Graham': 0.15, 'Residual': 0.05}
				weighted_sum = 0
				total_weight = 0
				
				for method, value in valuations.items():
					weight = weights.get(method, 0.1)
					weighted_sum += value * weight
					total_weight += weight
				
				self.intrinsic_value = weighted_sum / total_weight if total_weight > 0 else 0
			else:
				self.intrinsic_value = 0
				
		except Exception as e:
			frappe.log_error(f"Error calculating intrinsic value: {str(e)}", "Intrinsic Value Calculation Error")
			self.intrinsic_value = 0

	def _calculate_dcf_value(self):
		"""Calculate Discounted Cash Flow (DCF) value"""
		try:
			if not self.cash_flow:
				return None
			
			cash_flow_data = json.loads(self.cash_flow)
			ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
			
			# Extract historical free cash flows
			fcf_values = []
			years = []
			for date_key, data in cash_flow_data.items():
				if data.get('Free Cash Flow') and data['Free Cash Flow'] > 0:
					fcf_values.append(data['Free Cash Flow'])
					years.append(date_key[:4])
			
			if len(fcf_values) < 2:
				return None
			
			# Calculate average growth rate from historical data
			growth_rates = []
			for i in range(1, len(fcf_values)):
				if fcf_values[i-1] > 0:
					growth_rate = (fcf_values[i] - fcf_values[i-1]) / fcf_values[i-1]
					growth_rates.append(growth_rate)
			
			if not growth_rates:
				return None
			
			avg_growth_rate = sum(growth_rates) / len(growth_rates)
			# Cap growth rate to reasonable bounds
			avg_growth_rate = max(-0.5, min(0.5, avg_growth_rate))
			
			# Use WACC or estimated discount rate
			beta = ticker_info.get('beta', 1.0)
			risk_free_rate = 0.04  # Assume 4% risk-free rate
			market_premium = 0.08  # Assume 8% market risk premium
			discount_rate = risk_free_rate + beta * market_premium
			
			# Project FCF for next 5 years
			current_fcf = fcf_values[-1]
			projected_fcf = []
			for year in range(1, 6):
				projected_fcf.append(current_fcf * ((1 + avg_growth_rate) ** year))
			
			# Terminal value (assume 2% perpetual growth)
			terminal_growth = 0.02
			terminal_value = projected_fcf[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
			
			# Discount all cash flows to present value
			pv_fcf = sum([fcf / ((1 + discount_rate) ** (i + 1)) for i, fcf in enumerate(projected_fcf)])
			pv_terminal = terminal_value / ((1 + discount_rate) ** 5)
			
			enterprise_value = pv_fcf + pv_terminal
			
			# Subtract net debt and divide by shares outstanding
			total_debt = 0
			cash = 0
			shares_outstanding = ticker_info.get('sharesOutstanding', 1)
			
			if self.balance_sheet:
				balance_data = json.loads(self.balance_sheet)
				latest_balance = next(iter(balance_data.values())) if balance_data else {}
				total_debt = latest_balance.get('Total Debt', 0) or 0
				cash = latest_balance.get('Cash And Cash Equivalents', 0) or 0
			
			net_debt = total_debt - cash
			equity_value = enterprise_value - net_debt
			
			# Convert to per-share value (assuming values are in company's reporting currency)
			# Need to convert from company currency to USD if different
			financial_currency = ticker_info.get('financialCurrency', 'USD')
			price_currency = ticker_info.get('currency', 'USD')
			
			if shares_outstanding > 0:
				per_share_value = equity_value / shares_outstanding
				
				# Simple currency conversion approximation
				if financial_currency == 'TWD' and price_currency == 'USD':
					per_share_value = per_share_value / 31.5  # Approximate TWD/USD rate
				
				return per_share_value
			
			return None
			
		except Exception as e:
			frappe.log_error(f"Error in DCF calculation: {str(e)}", "DCF Calculation Error")
			return None

	def _calculate_ddm_value(self):
		"""Calculate Dividend Discount Model (DDM) value"""
		try:
			if not self.dividends:
				return None
			
			dividends_data = json.loads(self.dividends)
			ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
			
			# Extract annual dividends
			annual_dividends = {}
			for date_str, dividend in dividends_data.items():
				year = date_str[:4]
				if year not in annual_dividends:
					annual_dividends[year] = 0
				annual_dividends[year] += dividend
			
			if len(annual_dividends) < 3:
				return None
			
			# Calculate dividend growth rate
			years = sorted(annual_dividends.keys())
			recent_years = years[-5:]  # Last 5 years
			
			growth_rates = []
			for i in range(1, len(recent_years)):
				prev_div = annual_dividends[recent_years[i-1]]
				curr_div = annual_dividends[recent_years[i]]
				if prev_div > 0:
					growth_rate = (curr_div - prev_div) / prev_div
					growth_rates.append(growth_rate)
			
			if not growth_rates:
				return None
			
			avg_dividend_growth = sum(growth_rates) / len(growth_rates)
			# Cap dividend growth to reasonable bounds
			avg_dividend_growth = max(-0.2, min(0.15, avg_dividend_growth))
			
			# Required rate of return (cost of equity)
			beta = ticker_info.get('beta', 1.0)
			risk_free_rate = 0.04
			market_premium = 0.08
			required_return = risk_free_rate + beta * market_premium
			
			# Current annual dividend
			current_dividend = annual_dividends[years[-1]]
			
			# Gordon Growth Model: DDM = D1 / (r - g)
			if required_return > avg_dividend_growth:
				next_dividend = current_dividend * (1 + avg_dividend_growth)
				ddm_value = next_dividend / (required_return - avg_dividend_growth)
				return ddm_value
			
			return None
			
		except Exception as e:
			frappe.log_error(f"Error in DDM calculation: {str(e)}", "DDM Calculation Error")
			return None

	def _calculate_pe_value(self):
		"""Calculate P/E based valuation"""
		try:
			if not self.profit_loss:
				return None
			
			profit_loss_data = json.loads(self.profit_loss)
			ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
			
			# Get current EPS
			current_eps = ticker_info.get('trailingEps') or ticker_info.get('epsTrailingTwelveMonths')
			if not current_eps:
				return None
			
			# Calculate normalized P/E ratio based on industry
			sector = ticker_info.get('sector', '')
			
			# Industry average P/E ratios (approximate)
			industry_pe_ratios = {
				'Technology': 25,
				'Healthcare': 20,
				'Consumer Cyclical': 15,
				'Consumer Defensive': 18,
				'Financial Services': 12,
				'Energy': 14,
				'Materials': 16,
				'Industrials': 18,
				'Utilities': 16,
				'Real Estate': 20,
				'Communication Services': 22
			}
			
			industry_pe = industry_pe_ratios.get(sector, 18)  # Default to 18 if sector not found
			
			# Apply some discount/premium based on company quality metrics
			roe = ticker_info.get('returnOnEquity', 0)
			debt_to_equity = ticker_info.get('debtToEquity', 0)
			
			# Adjust P/E based on financial health
			pe_adjustment = 1.0
			if roe > 0.15:  # High ROE
				pe_adjustment += 0.1
			if roe < 0.05:  # Low ROE
				pe_adjustment -= 0.1
			if debt_to_equity > 0.5:  # High debt
				pe_adjustment -= 0.1
			
			adjusted_pe = industry_pe * pe_adjustment
			pe_value = current_eps * adjusted_pe
			
			return pe_value
			
		except Exception as e:
			frappe.log_error(f"Error in P/E calculation: {str(e)}", "P/E Calculation Error")
			return None

	def _calculate_book_value(self):
		"""Calculate asset-based book value"""
		try:
			ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
			
			book_value_per_share = ticker_info.get('bookValue')
			if not book_value_per_share:
				return None
			
			# Apply discount/premium based on asset quality
			roe = ticker_info.get('returnOnEquity', 0)
			roa = ticker_info.get('returnOnAssets', 0)
			
			# Price-to-book multiplier based on profitability
			pb_multiplier = 1.0
			if roe > 0.15 and roa > 0.08:  # High quality assets
				pb_multiplier = 1.2
			elif roe > 0.10 and roa > 0.05:  # Good quality assets
				pb_multiplier = 1.1
			elif roe < 0.05 or roa < 0.02:  # Poor quality assets
				pb_multiplier = 0.8
			
			asset_based_value = book_value_per_share * pb_multiplier
			
			return asset_based_value
			
		except Exception as e:
			frappe.log_error(f"Error in book value calculation: {str(e)}", "Book Value Calculation Error")
			return None

	def _calculate_graham_formula(self):
		"""Calculate Benjamin Graham's intrinsic value formula"""
		try:
			ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
			
			eps = ticker_info.get('trailingEps') or ticker_info.get('epsTrailingTwelveMonths')
			if not eps or eps <= 0:
				return None
			
			# Estimate growth rate from earnings growth
			earnings_growth = ticker_info.get('earningsGrowth', 0)
			if earnings_growth:
				growth_rate = earnings_growth * 100  # Convert to percentage
			else:
				growth_rate = 5  # Conservative default
			
			# Cap growth rate
			growth_rate = max(0, min(25, growth_rate))
			
			# Graham Formula: V = EPS × (8.5 + 2g) × 4.4 / Y
			# Where: EPS = current earnings per share
			#        g = growth rate
			#        Y = current AAA corporate bond yield (approximate with 4.5%)
			
			aaa_yield = 4.5  # Approximate AAA corporate bond yield
			
			graham_value = eps * (8.5 + 2 * growth_rate) * 4.4 / aaa_yield
			
			return graham_value
			
		except Exception as e:
			frappe.log_error(f"Error in Graham formula calculation: {str(e)}", "Graham Formula Error")
			return None

	def _calculate_residual_income(self):
		"""Calculate Residual Income Model value"""
		try:
			if not self.balance_sheet:
				return None
			
			ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
			balance_data = json.loads(self.balance_sheet)
			
			# Get current book value per share
			book_value_per_share = ticker_info.get('bookValue')
			if not book_value_per_share:
				return None
			
			# Get ROE and cost of equity
			roe = ticker_info.get('returnOnEquity', 0)
			if not roe:
				return None
			
			# Cost of equity using CAPM
			beta = ticker_info.get('beta', 1.0)
			risk_free_rate = 0.04
			market_premium = 0.08
			cost_of_equity = risk_free_rate + beta * market_premium
			
			# Calculate residual income
			# RI = ROE - Cost of Equity
			residual_income_rate = roe - cost_of_equity
			
			if residual_income_rate <= 0:
				return book_value_per_share  # If no residual income, value = book value
			
			# Assume residual income declines over time
			projection_years = 5
			residual_value = 0
			
			for year in range(1, projection_years + 1):
				# Declining residual income
				yearly_ri = residual_income_rate * book_value_per_share * (0.9 ** (year - 1))
				discounted_ri = yearly_ri / ((1 + cost_of_equity) ** year)
				residual_value += discounted_ri
			
			# Terminal value (assume residual income becomes 0)
			total_value = book_value_per_share + residual_value
			
			return total_value
			
		except Exception as e:
			frappe.log_error(f"Error in residual income calculation: {str(e)}", "Residual Income Error")
			return None

	def calculate_fair_value(self):
		"""Calculate fair value"""
		"""The market-implied value of a stock, considering both fundamentals and market conditions."""
		if self.security_type == "Cash":
			self.fair_value = 1.0
			return
		
		try:
			# Fair value combines intrinsic value with market sentiment and technical factors
			if not self.intrinsic_value:
				self.calculate_intrinsic_value()
			
			if not self.intrinsic_value:
				self.fair_value = 0
				return
			
			# Start with intrinsic value as base
			fair_value = self.intrinsic_value
			
			# Apply market sentiment adjustments
			if self.ticker_info:
				ticker_info = json.loads(self.ticker_info)
				
				# Technical indicators adjustments
				current_price = self.current_price or 0
				if current_price > 0:
					# Price momentum factor
					fifty_day_avg = ticker_info.get('fiftyDayAverage', current_price)
					two_hundred_day_avg = ticker_info.get('twoHundredDayAverage', current_price)
					
					# If price is above moving averages, slight premium
					momentum_factor = 1.0
					if current_price > fifty_day_avg and current_price > two_hundred_day_avg:
						momentum_factor = 1.05  # 5% premium for positive momentum
					elif current_price < fifty_day_avg and current_price < two_hundred_day_avg:
						momentum_factor = 0.95  # 5% discount for negative momentum
					
					fair_value *= momentum_factor
				
				# Market cap factor (large caps tend to trade closer to fair value)
				market_cap = ticker_info.get('marketCap', 0)
				if market_cap > 50_000_000_000:  # Large cap (>$50B)
					volatility_discount = 0.98  # Slight discount for stability
				elif market_cap < 2_000_000_000:  # Small cap (<$2B)
					volatility_discount = 0.92  # Higher discount for volatility
				else:  # Mid cap
					volatility_discount = 0.95
				
				fair_value *= volatility_discount
				
				# Liquidity factor (based on average volume)
				avg_volume = ticker_info.get('averageVolume', 0)
				if avg_volume < 100_000:  # Low liquidity
					fair_value *= 0.90  # Apply liquidity discount
				
				# Analyst sentiment (if available)
				target_price = ticker_info.get('targetMeanPrice')
				if target_price and target_price > 0:
					# Weight analyst target price at 20%
					analyst_weight = 0.2
					fair_value = fair_value * (1 - analyst_weight) + target_price * analyst_weight
			
			# Market conditions adjustment
			# In bear markets, apply additional discount; in bull markets, slight premium
			# This could be enhanced with market index analysis
			market_condition_factor = 1.0  # Neutral assumption
			
			# Apply final market condition adjustment
			fair_value *= market_condition_factor
			
			# Ensure fair value is reasonable (not negative)
			self.fair_value = max(0, fair_value)
			
		except Exception as e:
			frappe.log_error(f"Error calculating fair value: {str(e)}", "Fair Value Calculation Error")
			self.fair_value = 0

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
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
		self.calculate_intrinsic_value()
		self.calculate_fair_value()
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
		"""Set comprehensive alert analyzing all valuation metrics"""
		self.is_alert = 0
		self.alert_details = ""
		
		if not self.current_price or self.current_price <= 0:
			return
		
		# Get all relevant values with safe defaults
		current_price = flt(self.current_price)
		intrinsic_value = flt(self.intrinsic_value or 0)
		fair_value = flt(self.fair_value or 0)
		ai_buy_price = flt(self.suggestion_buy_price or 0)
		ai_sell_price = flt(self.suggestion_sell_price or 0)
		currency = self.currency or ""
		
		alert_messages = []
		alert_triggered = False
		
		# 1. AI-based alerts (highest priority)
		if ai_buy_price > 0 and current_price <= ai_buy_price:
			alert_triggered = True
			discount_pct = ((ai_buy_price - current_price) / ai_buy_price) * 100
			alert_messages.append(f"🟢 **AI BUY SIGNAL**: Current price {currency} {current_price:.2f} is {discount_pct:.1f}% below AI buy target of {currency} {ai_buy_price:.2f}")
		
		if ai_sell_price > 0 and current_price >= ai_sell_price:
			alert_triggered = True
			premium_pct = ((current_price - ai_sell_price) / ai_sell_price) * 100
			alert_messages.append(f"🔴 **AI SELL SIGNAL**: Current price {currency} {current_price:.2f} is {premium_pct:.1f}% above AI sell target of {currency} {ai_sell_price:.2f}")
		
		# 2. Fundamental value alerts
		if intrinsic_value > 0:
			intrinsic_ratio = current_price / intrinsic_value
			
			if intrinsic_ratio <= 0.7:  # Trading at 30%+ discount to intrinsic value
				alert_triggered = True
				discount_pct = ((intrinsic_value - current_price) / intrinsic_value) * 100
				alert_messages.append(f"💎 **DEEP VALUE**: Price {currency} {current_price:.2f} is {discount_pct:.1f}% below intrinsic value of {currency} {intrinsic_value:.2f}")
			
			elif intrinsic_ratio <= 0.85:  # Trading at 15%+ discount
				alert_triggered = True
				discount_pct = ((intrinsic_value - current_price) / intrinsic_value) * 100
				alert_messages.append(f"📈 **UNDERVALUED**: Price {currency} {current_price:.2f} is {discount_pct:.1f}% below intrinsic value of {currency} {intrinsic_value:.2f}")
			
			elif intrinsic_ratio >= 1.5:  # Trading at 50%+ premium
				alert_triggered = True
				premium_pct = ((current_price - intrinsic_value) / intrinsic_value) * 100
				alert_messages.append(f"⚠️ **OVERVALUED**: Price {currency} {current_price:.2f} is {premium_pct:.1f}% above intrinsic value of {currency} {intrinsic_value:.2f}")
			
			elif intrinsic_ratio >= 1.2:  # Trading at 20%+ premium
				alert_triggered = True
				premium_pct = ((current_price - intrinsic_value) / intrinsic_value) * 100
				alert_messages.append(f"📉 **EXPENSIVE**: Price {currency} {current_price:.2f} is {premium_pct:.1f}% above intrinsic value of {currency} {intrinsic_value:.2f}")
		
		# 3. Fair value alerts (market-adjusted)
		if fair_value > 0:
			fair_ratio = current_price / fair_value
			
			if fair_ratio <= 0.8:  # 20%+ discount to fair value
				if not any("DEEP VALUE" in msg or "UNDERVALUED" in msg for msg in alert_messages):
					alert_triggered = True
					discount_pct = ((fair_value - current_price) / fair_value) * 100
					alert_messages.append(f"🎯 **BELOW FAIR VALUE**: Price {currency} {current_price:.2f} is {discount_pct:.1f}% below fair value of {currency} {fair_value:.2f}")
			
			elif fair_ratio >= 1.25:  # 25%+ premium to fair value
				if not any("OVERVALUED" in msg or "EXPENSIVE" in msg for msg in alert_messages):
					alert_triggered = True
					premium_pct = ((current_price - fair_value) / fair_value) * 100
					alert_messages.append(f"🚨 **ABOVE FAIR VALUE**: Price {currency} {current_price:.2f} is {premium_pct:.1f}% above fair value of {currency} {fair_value:.2f}")
		
		# 4. Cross-validation insights
		if intrinsic_value > 0 and fair_value > 0:
			iv_fv_ratio = intrinsic_value / fair_value
			
			if iv_fv_ratio >= 1.3:  # Intrinsic value much higher than fair value
				alert_messages.append(f"💡 **INSIGHT**: Fundamental analysis suggests {((iv_fv_ratio - 1) * 100):.1f}% more upside than market expects")
			elif iv_fv_ratio <= 0.8:  # Fair value much higher than intrinsic value
				alert_messages.append(f"⚡ **INSIGHT**: Market expectations exceed fundamental value by {((1/iv_fv_ratio - 1) * 100):.1f}%")
		
		# 5. AI vs Fundamental analysis comparison
		if ai_buy_price > 0 and intrinsic_value > 0:
			ai_fundamental_ratio = ai_buy_price / intrinsic_value
			
			if ai_fundamental_ratio >= 1.2:
				alert_messages.append(f"🤖 **AI vs FUNDAMENTAL**: AI suggests higher value ({currency} {ai_buy_price:.2f}) than fundamental analysis ({currency} {intrinsic_value:.2f})")
			elif ai_fundamental_ratio <= 0.8:
				alert_messages.append(f"📊 **AI vs FUNDAMENTAL**: Fundamental analysis suggests higher value ({currency} {intrinsic_value:.2f}) than AI ({currency} {ai_buy_price:.2f})")
			else:
				alert_messages.append(f"✅ **CONSENSUS**: AI and fundamental analysis are aligned around {currency} {((ai_buy_price + intrinsic_value) / 2):.2f}")
		
		# 6. Volatility and risk assessment
		if intrinsic_value > 0 and fair_value > 0:
			value_spread = abs(intrinsic_value - fair_value)
			avg_value = (intrinsic_value + fair_value) / 2
			uncertainty_pct = (value_spread / avg_value) * 100
			
			if uncertainty_pct > 30:
				alert_messages.append(f"⚠️ **HIGH UNCERTAINTY**: Large spread between valuations suggests higher risk/reward potential")
			elif uncertainty_pct < 10:
				alert_messages.append(f"✅ **LOW UNCERTAINTY**: Valuation models show good consensus")
		
		# Set final alert status and details
		self.is_alert = 1 if alert_triggered else 0
		
		if alert_messages:
			self.alert_details = "\n\n".join(alert_messages)
		else:
			# No alerts, but provide summary
			if intrinsic_value > 0:
				iv_variance = ((current_price - intrinsic_value) / intrinsic_value) * 100
				self.alert_details = f"📊 **FAIR PRICED**: Current price {currency} {current_price:.2f} is within normal range of intrinsic value {currency} {intrinsic_value:.2f} ({iv_variance:+.1f}%)"

	def calculate_intrinsic_value(self):
		"""Calculate intrinsic value using intelligently selected valuation methods"""
		"""The true, fundamental worth of a stock based on its underlying business performance, cash flows, and assets."""
		if self.security_type == "Cash":
			self.intrinsic_value = 1.0
			return
		
		try:
			# Intelligently select the best valuation methods for this company
			best_methods = self._select_best_valuation_methods()
			
			if not best_methods:
				self.intrinsic_value = 0
				return
			
			valuations = {}
			
			# Calculate only the selected methods
			for method in best_methods:
				if method == 'DCF':
					value = self._calculate_dcf_value()
				elif method == 'DDM':
					value = self._calculate_ddm_value()
				elif method == 'P/E':
					value = self._calculate_pe_value()
				elif method == 'Book':
					value = self._calculate_book_value()
				elif method == 'Graham':
					value = self._calculate_graham_formula()
				elif method == 'Residual':
					value = self._calculate_residual_income()
				else:
					continue
				
				if value and value > 0:
					valuations[method] = value
			
			# Calculate average of valid methods (equal weighting for selected methods)
			if valuations:
				self.intrinsic_value = sum(valuations.values()) / len(valuations)
			else:
				self.intrinsic_value = 0
				
		except Exception as e:
			frappe.log_error(f"Error calculating intrinsic value: {str(e)}", "Intrinsic Value Calculation Error")
			self.intrinsic_value = 0

	def _select_best_valuation_methods(self):
		"""Intelligently select the most appropriate valuation methods based on sector/industry and company characteristics"""
		try:
			if not self.ticker_info:
				return ['Book']  # Fallback to book value if no data
			
			ticker_info = json.loads(self.ticker_info)
			
			# Get sector and industry information
			sector = ticker_info.get('sector', '').lower()
			industry = ticker_info.get('industry', '').lower()
			
			# Analyze company characteristics
			has_dividends = self._has_consistent_dividends()
			has_stable_earnings = self._has_stable_earnings()
			has_positive_fcf = self._has_positive_free_cash_flow()
			is_asset_heavy = self._is_asset_heavy_business()
			is_growth_company = self._is_growth_company()
			
			# Sector-specific valuation method selection
			selected_methods = self._get_sector_specific_methods(sector, industry, {
				'has_dividends': has_dividends,
				'has_stable_earnings': has_stable_earnings,
				'has_positive_fcf': has_positive_fcf,
				'is_asset_heavy': is_asset_heavy,
				'is_growth_company': is_growth_company
			})
			
			if selected_methods:
				return selected_methods
			
			# Fallback to generic logic if sector not recognized
			return self._get_generic_valuation_methods(has_dividends, has_stable_earnings, 
													 has_positive_fcf, is_asset_heavy, is_growth_company)
			
		except Exception as e:
			frappe.log_error(f"Error selecting valuation methods: {str(e)}", "Method Selection Error")
			return ['Book']  # Safe fallback
	
	def _get_sector_specific_methods(self, sector, industry, characteristics):
		"""Select valuation methods based on specific sector/industry characteristics"""
		
		# Technology Sector
		if 'technology' in sector or any(tech in industry for tech in ['software', 'semiconductor', 'computer', 'internet']):
			if characteristics['has_positive_fcf']:
				methods = ['DCF']
				if characteristics['is_growth_company']:
					# Growth tech companies - focus on DCF and growth-adjusted P/E
					if characteristics['has_stable_earnings']:
						methods.append('P/E')
				else:
					# Mature tech companies
					methods.extend(['P/E'])
					if characteristics['has_dividends']:
						methods.append('DDM')
				return methods
			else:
				# Tech companies without positive FCF - use P/E if profitable
				return ['P/E'] if characteristics['has_stable_earnings'] else ['Book']
		
		# Financial Services
		elif 'financial' in sector or any(fin in industry for fin in ['bank', 'insurance', 'reit', 'real estate investment trust']):
			methods = ['Book']  # Book value is primary for financial companies
			
			# Banks and traditional financial institutions
			if any(bank in industry for bank in ['bank', 'credit', 'lending']):
				if characteristics['has_stable_earnings']:
					methods.append('P/E')  # But use financial-adjusted P/E metrics
				if characteristics['has_dividends']:
					methods.append('DDM')
			
			# REITs and real estate
			elif 'reit' in industry or 'real estate' in industry:
				methods = ['DDM', 'Book']  # REITs must distribute dividends
			
			# Insurance companies
			elif 'insurance' in industry:
				methods = ['Book', 'Residual']  # Book value and residual income for insurers
				if characteristics['has_dividends']:
					methods.append('DDM')
			
			return methods
		
		# Utilities
		elif 'utilities' in sector or 'utility' in industry:
			methods = ['DDM']  # Utilities are dividend-focused
			if characteristics['has_positive_fcf']:
				methods.append('DCF')  # Stable, predictable cash flows
			if characteristics['is_asset_heavy']:
				methods.append('Book')  # Infrastructure assets
			return methods
		
		# Energy & Oil/Gas
		elif 'energy' in sector or any(energy in industry for energy in ['oil', 'gas', 'petroleum', 'mining']):
			if characteristics['has_positive_fcf'] and not self._is_commodity_price_volatile():
				methods = ['DCF']  # When commodity prices are stable
			else:
				methods = ['Book']  # Asset replacement value during volatile periods
			
			if characteristics['has_stable_earnings']:
				methods.append('P/E')  # Normalized P/E during stable periods
			
			return methods
		
		# Healthcare & Pharmaceuticals
		elif 'healthcare' in sector or any(health in industry for health in ['pharmaceutical', 'biotechnology', 'medical', 'drug']):
			methods = []
			if characteristics['has_positive_fcf']:
				methods.append('DCF')
			if characteristics['has_stable_earnings']:
				methods.append('P/E')  # Adjusted for R&D expenses
			
			# Mature pharma companies often pay dividends
			if characteristics['has_dividends'] and not characteristics['is_growth_company']:
				methods.append('DDM')
			
			return methods if methods else ['P/E']
		
		# Consumer Staples
		elif 'consumer defensive' in sector or 'consumer staples' in sector:
			methods = ['P/E']  # Stable earnings make P/E reliable
			if characteristics['has_dividends']:
				methods.append('DDM')  # Many staples pay consistent dividends
			methods.append('Graham')  # Graham formula works well for stable companies
			return methods
		
		# Consumer Discretionary/Cyclical
		elif 'consumer cyclical' in sector or 'consumer discretionary' in sector:
			if characteristics['has_stable_earnings']:
				methods = ['P/E']
			else:
				methods = ['Book']  # During cyclical downturns
			
			if characteristics['has_positive_fcf']:
				methods.append('DCF')
			
			return methods
		
		# Materials & Mining
		elif 'materials' in sector or 'basic materials' in sector or any(material in industry for material in ['mining', 'steel', 'aluminum', 'chemicals']):
			methods = ['Book']  # Asset replacement cost is important
			
			# During stable periods, earnings-based methods work
			if characteristics['has_stable_earnings']:
				methods.append('P/E')
			
			if characteristics['has_positive_fcf'] and not self._is_commodity_price_volatile():
				methods.append('DCF')
			
			return methods
		
		# Industrials
		elif 'industrials' in sector:
			methods = []
			if characteristics['has_positive_fcf']:
				methods.append('DCF')
			if characteristics['has_stable_earnings']:
				methods.append('P/E')
			if characteristics['is_asset_heavy']:
				methods.append('Book')
			
			return methods if methods else ['P/E']
		
		# Communication Services
		elif 'communication' in sector or 'telecommunications' in sector:
			methods = []
			if characteristics['has_positive_fcf']:
				methods.append('DCF')  # Predictable subscription revenue
			if characteristics['has_dividends']:
				methods.append('DDM')  # Many telcos pay dividends
			if characteristics['has_stable_earnings']:
				methods.append('P/E')
			
			return methods if methods else ['Book']
		
		# Real Estate (non-REIT)
		elif 'real estate' in sector and 'reit' not in industry:
			methods = ['Book']  # Property asset value
			if characteristics['has_positive_fcf']:
				methods.append('DCF')
			if characteristics['has_dividends']:
				methods.append('DDM')
			return methods
		
		# If sector not specifically handled, return empty to use generic logic
		return []
	
	def _get_generic_valuation_methods(self, has_dividends, has_stable_earnings, has_positive_fcf, is_asset_heavy, is_growth_company):
		"""Fallback generic valuation method selection"""
		
		# Growth companies with positive FCF
		if is_growth_company and has_positive_fcf:
			selected_methods = ['DCF']
			if has_stable_earnings:
				selected_methods.append('P/E')
			return selected_methods
		
		# Dividend aristocrats (mature dividend-paying companies)
		if has_dividends and has_stable_earnings:
			selected_methods = ['DDM', 'P/E']
			if has_positive_fcf:
				selected_methods.append('DCF')
			return selected_methods
		
		# Asset-heavy businesses
		if is_asset_heavy:
			selected_methods = ['Book']
			if has_stable_earnings:
				selected_methods.append('P/E')
			return selected_methods
		
		# Value stocks with stable earnings
		if has_stable_earnings and not is_growth_company:
			selected_methods = ['P/E', 'Graham']
			if has_positive_fcf:
				selected_methods.append('DCF')
			return selected_methods
		
		# Companies with positive FCF but irregular earnings
		if has_positive_fcf and not has_stable_earnings:
			return ['DCF']
		
		# Profitable companies (fallback)
		if has_stable_earnings:
			return ['P/E']
		
		# Last resort - use book value
		return ['Book']
	
	def _has_consistent_dividends(self):
		"""Check if company has paid consistent dividends"""
		try:
			if not self.dividends:
				return False
			
			dividends_data = json.loads(self.dividends)
			if len(dividends_data) < 3:  # Need at least 3 years
				return False
			
			# Group by year and check consistency
			annual_dividends = {}
			for date_str, dividend in dividends_data.items():
				year = date_str[:4]
				if year not in annual_dividends:
					annual_dividends[year] = 0
				annual_dividends[year] += dividend
			
			# Check if dividends were paid in recent years
			years = sorted(annual_dividends.keys())
			recent_years = years[-3:]  # Last 3 years
			
			for year in recent_years:
				if annual_dividends[year] <= 0:
					return False
			
			return True
			
		except Exception:
			return False
	
	def _has_stable_earnings(self):
		"""Check if company has stable positive earnings"""
		try:
			if not self.ticker_info:
				return False
			
			ticker_info = json.loads(self.ticker_info)
			
			# Check current profitability
			trailing_eps = ticker_info.get('trailingEps') or ticker_info.get('epsTrailingTwelveMonths')
			if not trailing_eps or trailing_eps <= 0:
				return False
			
			# Check if profit margins are reasonable
			profit_margin = ticker_info.get('profitMargins', 0)
			if profit_margin < 0.02:  # Less than 2% margin
				return False
			
			# Check earnings volatility if available
			earnings_growth = ticker_info.get('earningsGrowth')
			if earnings_growth and abs(earnings_growth) > 0.5:  # Very volatile earnings
				return False
			
			return True
			
		except Exception:
			return False
	
	def _has_positive_free_cash_flow(self):
		"""Check if company generates consistent positive free cash flow"""
		try:
			if not self.cash_flow:
				return False
			
			cash_flow_data = json.loads(self.cash_flow)
			
			# Check recent FCF values
			positive_fcf_count = 0
			total_periods = 0
			
			for date_key, data in cash_flow_data.items():
				fcf = data.get('Free Cash Flow')
				if fcf is not None:
					total_periods += 1
					if fcf > 0:
						positive_fcf_count += 1
			
			# Require at least 70% of periods to have positive FCF
			return total_periods >= 2 and (positive_fcf_count / total_periods) >= 0.7
			
		except Exception:
			return False
	
	def _is_asset_heavy_business(self):
		"""Determine if this is an asset-heavy business"""
		try:
			if not self.ticker_info:
				return False
			
			ticker_info = json.loads(self.ticker_info)
			
			# Check sector
			sector = ticker_info.get('sector', '').lower()
			asset_heavy_sectors = [
				'utilities', 'energy', 'materials', 'real estate',
				'financial services', 'basic materials'
			]
			
			if any(heavy_sector in sector for heavy_sector in asset_heavy_sectors):
				return True
			
			# Check asset turnover ratio (if available)
			# Lower asset turnover indicates asset-heavy business
			# This would require balance sheet analysis
			if self.balance_sheet:
				try:
					balance_data = json.loads(self.balance_sheet)
					latest_balance = next(iter(balance_data.values())) if balance_data else {}
					total_assets = latest_balance.get('Total Assets', 0)
					
					# If we have revenue data, calculate asset turnover
					revenue = ticker_info.get('totalRevenue', 0)
					if total_assets > 0 and revenue > 0:
						asset_turnover = revenue / total_assets
						return asset_turnover < 0.5  # Low asset turnover
				except Exception:
					pass
			
			return False
			
		except Exception:
			return False
	
	def _is_growth_company(self):
		"""Determine if this is a growth company"""
		try:
			if not self.ticker_info:
				return False
			
			ticker_info = json.loads(self.ticker_info)
			
			# Check growth metrics
			revenue_growth = ticker_info.get('revenueGrowth', 0)
			earnings_growth = ticker_info.get('earningsGrowth', 0)
			
			# High growth thresholds
			if revenue_growth > 0.15 or earnings_growth > 0.15:  # 15%+ growth
				return True
			
			# Check P/E ratio (growth companies typically have higher P/E)
			pe_ratio = ticker_info.get('trailingPE', 0)
			if pe_ratio > 25:  # High P/E suggests growth expectations
				return True
			
			# Check sector (tech companies are often growth-oriented)
			sector = ticker_info.get('sector', '').lower()
			if 'technology' in sector:
				return True
			
			return False
			
		except Exception:
			return False
	
	def _is_financial_company(self):
		"""Check if this is a financial services company"""
		try:
			if not self.ticker_info:
				return False
			
			ticker_info = json.loads(self.ticker_info)
			sector = ticker_info.get('sector', '').lower()
			industry = ticker_info.get('industry', '').lower()
			
			financial_keywords = [
				'financial', 'bank', 'insurance', 'reit', 'real estate investment trust',
				'asset management', 'investment', 'credit'
			]
			
			return any(keyword in sector or keyword in industry for keyword in financial_keywords)
			
		except Exception:
			return False

	def _is_commodity_price_volatile(self):
		"""Check if commodity prices are currently volatile for energy/materials companies"""
		try:
			# This is a simplified heuristic - in production, you might want to check:
			# - Oil price volatility (VIX for oil)
			# - Commodity indices volatility
			# - Company's revenue/earnings volatility
			
			if not self.ticker_info:
				return True  # Assume volatile if no data
			
			ticker_info = json.loads(self.ticker_info)
			
			# Check earnings volatility as a proxy for commodity price impact
			earnings_growth = ticker_info.get('earningsGrowth')
			if earnings_growth and abs(earnings_growth) > 0.5:  # >50% earnings volatility
				return True
			
			# Check profit margin volatility
			profit_margin = ticker_info.get('profitMargins', 0)
			if profit_margin < 0.05:  # Very low margins suggest commodity pressure
				return True
			
			# Default to assuming some volatility for commodity-dependent sectors
			return True
			
		except Exception:
			return True  # Conservative assumption

	def _get_current_risk_free_rate(self, country='United States'):
		"""Get current risk-free rate from Yahoo Finance treasury data"""
		try:
			# Map countries to their treasury bond symbols on Yahoo Finance
			treasury_symbols = {
				'United States': '^TNX',      # 10-Year Treasury Yield
				'Germany': '^TNX-DE',         # 10-Year German Bund (if available)
				'United Kingdom': '^TNXUK',   # 10-Year UK Gilt
				'Japan': '^TNX-JP',           # 10-Year Japanese Government Bond
				'Canada': '^TNX-CA',          # 10-Year Canadian Government Bond
				'Australia': '^TNX-AU',       # 10-Year Australian Government Bond
				'France': '^TNX-FR',          # 10-Year French Government Bond
				'Switzerland': '^TNX-CH',     # 10-Year Swiss Government Bond
			}
			
			symbol = treasury_symbols.get(country)
			if not symbol:
				# For unsupported countries, use US treasury as proxy with country risk adjustment
				symbol = '^TNX'
			
			# Fetch live treasury rate from Yahoo Finance
			treasury_ticker = yf.Ticker(symbol)
			treasury_info = treasury_ticker.get_info()
			
			# Get the current yield (usually in the 'regularMarketPrice' field for bond yields)
			current_yield = treasury_info.get('regularMarketPrice') or treasury_info.get('previousClose')
			
			if current_yield and current_yield > 0:
				# Convert percentage to decimal (Yahoo returns yields as percentages)
				risk_free_rate = current_yield / 100
				
				# Apply country risk premium for non-major economies
				if country not in ['United States', 'Germany', 'United Kingdom', 'Japan', 'Canada']:
					country_risk_premium = 0.005  # Add 0.5% country risk premium
					risk_free_rate += country_risk_premium
				
				return risk_free_rate
			
			# Fallback if live data is not available
			raise Exception("Live treasury data not available")
			
		except Exception as e:
			frappe.log_error(f"Error fetching live risk-free rate for {country}: {str(e)}", "Risk-Free Rate Fetch Error")
			
			# Fallback to reasonable estimates if live data fails
			fallback_rates = {
				'United States': 0.045,
				'Germany': 0.025,
				'United Kingdom': 0.040,
				'Japan': 0.015,
				'Canada': 0.040,
				'Australia': 0.042,
				'France': 0.028,
				'Switzerland': 0.018,
			}
			
			return fallback_rates.get(country, 0.035)
	
	def _analyze_fcf_quality(self, cash_flow_data, profit_loss_data):
		"""Analyze the quality and sustainability of free cash flows"""
		try:
			if not cash_flow_data or not profit_loss_data:
				return 1.0  # Neutral quality score
			
			quality_score = 1.0
			
			# Check FCF vs Net Income consistency
			fcf_values = []
			net_income_values = []
			
			for date_key in cash_flow_data.keys():
				fcf = cash_flow_data[date_key].get('Free Cash Flow')
				if fcf is not None:
					fcf_values.append(fcf)
				
				# Get corresponding net income
				if date_key in profit_loss_data:
					net_income = profit_loss_data[date_key].get('Net Income')
					if net_income is not None:
						net_income_values.append(net_income)
			
			if len(fcf_values) >= 3 and len(net_income_values) >= 3:
				# FCF should generally track with net income over time
				avg_fcf = sum(fcf_values) / len(fcf_values)
				avg_net_income = sum(net_income_values) / len(net_income_values)
				
				if avg_net_income > 0:
					fcf_conversion_ratio = avg_fcf / avg_net_income
					
					# Good FCF conversion (80-120% of net income)
					if 0.8 <= fcf_conversion_ratio <= 1.2:
						quality_score *= 1.0  # Neutral
					elif fcf_conversion_ratio > 1.2:
						quality_score *= 1.1  # High quality (generating more cash than earnings)
					elif fcf_conversion_ratio < 0.5:
						quality_score *= 0.8  # Poor quality (much lower cash than earnings)
			
			# Check FCF volatility
			if len(fcf_values) >= 3:
				fcf_mean = sum(fcf_values) / len(fcf_values)
				if fcf_mean != 0:
					fcf_volatility = sum([(fcf - fcf_mean) ** 2 for fcf in fcf_values]) / len(fcf_values)
					fcf_cv = (fcf_volatility ** 0.5) / abs(fcf_mean)  # Coefficient of variation
					
					# Lower volatility is better
					if fcf_cv < 0.3:  # Low volatility
						quality_score *= 1.05
					elif fcf_cv > 0.8:  # High volatility
						quality_score *= 0.9
			
			# Check for negative FCF years
			negative_fcf_years = sum(1 for fcf in fcf_values if fcf < 0)
			if len(fcf_values) > 0:
				negative_ratio = negative_fcf_years / len(fcf_values)
				if negative_ratio > 0.3:  # More than 30% negative years
					quality_score *= 0.85
			
			return max(0.5, min(1.3, quality_score))  # Cap between 0.5 and 1.3
			
		except Exception:
			return 1.0  # Neutral score on error

	def _calculate_dcf_value(self):
		"""Calculate Discounted Cash Flow (DCF) value with improved assumptions"""
		try:
			if not self.cash_flow:
				return None
			
			cash_flow_data = json.loads(self.cash_flow)
			ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
			
			# Extract historical free cash flows (need minimum 3 years for reliability)
			fcf_values = []
			years = []
			for date_key, data in cash_flow_data.items():
				fcf = data.get('Free Cash Flow')
				if fcf is not None:  # Include negative FCF for realistic analysis
					fcf_values.append(fcf)
					years.append(date_key[:4])
			
			if len(fcf_values) < 3:  # Require minimum 3 years
				return None
			
			# Sort by year to ensure chronological order
			fcf_year_pairs = list(zip(years, fcf_values))
			fcf_year_pairs.sort(key=lambda x: x[0])
			sorted_years, sorted_fcf = zip(*fcf_year_pairs)
			
			# Calculate growth rate with outlier filtering
			growth_rates = []
			for i in range(1, len(sorted_fcf)):
				if sorted_fcf[i-1] != 0:  # Avoid division by zero
					growth_rate = (sorted_fcf[i] - sorted_fcf[i-1]) / abs(sorted_fcf[i-1])
					# Filter extreme outliers (beyond -90% to +200%)
					if -0.9 <= growth_rate <= 2.0:
						growth_rates.append(growth_rate)
			
			if not growth_rates:
				return None
			
			# Use median instead of mean to reduce outlier impact
			growth_rates.sort()
			n = len(growth_rates)
			if n % 2 == 0:
				median_growth = (growth_rates[n//2-1] + growth_rates[n//2]) / 2
			else:
				median_growth = growth_rates[n//2]
			
			# Apply industry and company-specific growth constraints
			sector = ticker_info.get('sector', '').lower()
			market_cap = ticker_info.get('marketCap', 0)
			
			# Industry-specific growth caps
			if 'utility' in sector or 'financial' in sector:
				growth_cap = 0.15  # Mature industries
			elif 'technology' in sector or 'healthcare' in sector:
				growth_cap = 0.40  # High-growth potential
			else:
				growth_cap = 0.25  # General industries
			
			# Size-based adjustments (larger companies typically grow slower)
			if market_cap > 100_000_000_000:  # >$100B
				growth_cap *= 0.7
			elif market_cap < 2_000_000_000:  # <$2B
				growth_cap *= 1.3
			
			# Final growth rate with conservative bounds
			avg_growth_rate = max(-0.20, min(growth_cap, median_growth))
			
			# Dynamic discount rate calculation
			beta = ticker_info.get('beta', 1.0)
			beta = max(0.5, min(2.5, beta))  # Cap beta at reasonable bounds
			
			# Use dynamic risk-free rate based on country
			country = ticker_info.get('country', 'United States')
			risk_free_rate = self._get_current_risk_free_rate(country)
			market_premium = 0.065  # More conservative market premium
			
			# Add size premium for smaller companies
			size_premium = 0
			if market_cap < 2_000_000_000:  # Small cap
				size_premium = 0.02
			elif market_cap < 10_000_000_000:  # Mid cap
				size_premium = 0.01
			
			# Add financial risk premium based on debt levels
			debt_premium = 0
			debt_to_equity = ticker_info.get('debtToEquity', 0)
			if debt_to_equity > 1.0:  # High debt
				debt_premium = 0.015
			elif debt_to_equity > 0.5:  # Moderate debt
				debt_premium = 0.005
			
			discount_rate = risk_free_rate + beta * market_premium + size_premium + debt_premium
			
			# Improved FCF projection with declining growth rates
			current_fcf = sorted_fcf[-1]
			projected_fcf = []
			
			# Use declining growth rate model (high growth in early years, declining to mature rate)
			for year in range(1, 6):
				# Decline growth rate over time (fade to long-term growth)
				declining_factor = 1 - (year - 1) * 0.2  # Decline by 20% each year
				year_growth = avg_growth_rate * declining_factor
				
				# Apply minimum mature growth rate in later years
				mature_growth = min(0.03, avg_growth_rate)  # Max 3% mature growth
				if year >= 4:  # Years 4-5 use mature growth
					year_growth = mature_growth
				
				projected_fcf.append(current_fcf * ((1 + year_growth) ** year))
			
			# More conservative terminal value calculation
			# Terminal growth should not exceed long-term GDP growth
			country = ticker_info.get('country', 'United States')
			if country in ['United States', 'Canada', 'Germany', 'France', 'United Kingdom']:
				max_terminal_growth = 0.025  # 2.5% for developed markets
			elif country in ['China', 'India', 'Brazil', 'Mexico']:
				max_terminal_growth = 0.035  # 3.5% for emerging markets
			else:
				max_terminal_growth = 0.02  # 2% default
			
			# Terminal growth is the minimum of mature growth and economic growth cap
			terminal_growth = min(max_terminal_growth, mature_growth)
			
			# Calculate terminal value using exit multiple as sanity check
			terminal_fcf = projected_fcf[-1] * (1 + terminal_growth)
			terminal_value_perpetuity = terminal_fcf / (discount_rate - terminal_growth)
			
			# Alternative: Terminal value using exit multiple (10-15x FCF)
			exit_multiple = 12  # Conservative exit multiple
			terminal_value_multiple = projected_fcf[-1] * exit_multiple
			
			# Use the lower of perpetuity and multiple methods for conservatism
			terminal_value = min(terminal_value_perpetuity, terminal_value_multiple)
			
			# Discount all cash flows to present value
			pv_fcf = sum([fcf / ((1 + discount_rate) ** (i + 1)) for i, fcf in enumerate(projected_fcf)])
			pv_terminal = terminal_value / ((1 + discount_rate) ** 5)
			
			enterprise_value = pv_fcf + pv_terminal
			
			# Apply FCF quality adjustment
			if self.profit_loss:
				profit_loss_data = json.loads(self.profit_loss)
				fcf_quality_score = self._analyze_fcf_quality(cash_flow_data, profit_loss_data)
				enterprise_value *= fcf_quality_score
			
			# Subtract net debt and divide by shares outstanding
			total_debt = 0
			cash = 0
			shares_outstanding = ticker_info.get('sharesOutstanding', 1)
			
			if self.balance_sheet:
				balance_data = json.loads(self.balance_sheet)
				latest_balance = next(iter(balance_data.values())) if balance_data else {}
				total_debt = latest_balance.get('Total Debt', 0) or 0
				cash = latest_balance.get('Cash And Cash Equivalents', 0) or 0
				
				# Only subtract 50% of cash (assume rest is operational)
				operational_cash_buffer = 0.5
				excess_cash = cash * (1 - operational_cash_buffer)
			else:
				excess_cash = 0
			
			net_debt = total_debt - excess_cash
			equity_value = enterprise_value - net_debt
			
			# Convert to per-share value
			if shares_outstanding > 0:
				per_share_value = equity_value / shares_outstanding
				
				# Sanity check: ensure result is reasonable
				current_price = ticker_info.get('regularMarketPrice', 0) or self.current_price or 0
				if current_price > 0:
					# If DCF value is more than 5x or less than 0.2x current price, it's likely wrong
					price_ratio = per_share_value / current_price
					if price_ratio > 5.0 or price_ratio < 0.2:
						frappe.log_error(f"DCF value {per_share_value} seems unreasonable vs current price {current_price} (ratio: {price_ratio})", "DCF Sanity Check Warning")
						# Don't return None, but log the warning for investigation
				
				return max(0, per_share_value)  # Ensure non-negative value
			
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
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
		"""Calculate intrinsic value"""
		"""The true, fundamental worth of a stock based on its underlying business performance, cash flows, and assets."""
		pass

	def calculate_fair_value(self):
		"""Calculate fair value"""
		"""The market-implied value of a stock, considering both fundamentals and market conditions."""
		pass

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
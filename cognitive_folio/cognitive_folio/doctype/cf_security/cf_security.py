# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import json
import requests
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from openai import OpenAI

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
            self.fetch_current_price()

    @frappe.whitelist()
    def fetch_current_price(self):

        if self.security_type == "Cash":
            return {'success': False, 'error': _('Price is only for non-cash securities')}
        
        """Fetch the current price from Yahoo Finance"""
        try:
            ticker = yf.Ticker(self.symbol)
            ticker_info = ticker.get_info()
            self.ticker_info = frappe.as_json(ticker_info)
            self.currency = ticker_info['currency']
            self.current_price = ticker_info['regularMarketPrice']
            self.news = frappe.as_json(ticker.get_news())
            self.country = ticker_info.get('country', '')
            if self.country == "South Korea":
                self.country = "Korea, Republic of"
            if not self.region:
                self.region, self.subregion = get_country_region_from_api(self.country)
            self.save()
        except Exception as e:
            frappe.log_error(f"Error fetching current price: {str(e)}", "Fetch Current Price Error")
            frappe.throw("Error fetching current price. Please check the symbol.")
            
    def on_update(self):
        """Update related documents when a security is updated"""
        self.update_portfolio_holdings()
            
    def update_portfolio_holdings(self):
        """Update the value of portfolio holdings that contain this security"""
        if frappe.db.table_exists("CF Portfolio Holding"):
            holdings = frappe.get_all(
                "CF Portfolio Holding",
                filters={"security": self.name},
                fields=["name"]
            )
            
            for holding in holdings:
                # Trigger value recalculation in each holding
                holding_doc = frappe.get_doc("CF Portfolio Holding", holding.name)
                holding_doc.save()

    @frappe.whitelist()
    def generate_ai_suggestion(self):
        if self.security_type == "Cash":
            return {'success': False, 'error': _('AI suggestion is only for non-cash securities')}
        
        try:
            # Get OpenWebUI settings
            settings = frappe.get_single("CF Settings")
            client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
            model = settings.default_ai_model
            if not model:
                frappe.throw(_('Default AI model is not configured in CF Settings'))

            # Prepare data for the prompt_1
            ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
            
            news_json = json.loads(self.news) if self.news else []
            # Extract URLs from news data and format with # prefix
            news_urls = ["#" + item.get("content", {}).get("clickThroughUrl", {}).get("url", "") 
                            for item in news_json if item.get("content") and item.get("content").get("clickThroughUrl")]
            news = "\n".join(news_urls)
            
            # Create base prompt_1 with security data
            prompt_1 = f"""
            You own below security.
            Please analyze this security based on "Ticker Information" and "Recent News".
            
            Security: {self.security_name} ({self.symbol})
            Exchange: {self.stock_exchange}
            Sector: {self.sector}
            Industry: {self.industry}
            
            Ticker Information:
            {json.dumps(ticker_info, indent=2)}
            
            Recent News:
            {json.dumps(news, indent=2)}
            """                        
            
            # Add final instructions to the prompt_1
            prompt_1 += """
            
            Provide the following without mentioning your name:
            - A summary of the analysis.
            - A detailed analysis of the security.
            - A recommendation on whether to buy, hold, or sell this security.
            - Provide a risk assessment based on the analysis.
            - Provide a target price for the next 3 months.
            - Provide a target price for the next 6 months.
            - Provide a target price for the next 12 months.
            - Provide a risk/reward ratio based on the analysis.
            - Provide a volatility analysis based on the historical data.
            - Provide a sentiment analysis based on the news articles.
            - Provide a technical analysis based on the historical data.
            - Provide a fundamental analysis based on the financial data.
            - Provide a macroeconomic analysis based on the current economic conditions.
            - Provide a geopolitical analysis based on the current geopolitical conditions.
            - Provide a sector analysis based on the current sector conditions.
            - Provide a market analysis based on the current market conditions.
            - Provide a risk management strategy based on the analysis.
            - Provide a portfolio allocation strategy based on the analysis.
            - Provide a diversification strategy based on the analysis.
            - Provide a rebalancing strategy based on the analysis.
            - Provide a tax strategy based on the analysis.
            - Provide a retirement strategy based on the analysis.
            - Provide an estate planning strategy based on the analysis.
            - Provide a wealth management strategy based on the analysis.
            - Provide a financial planning strategy based on the analysis.
            - Provide a risk tolerance assessment based on the analysis.
            - Provide a financial goals assessment based on the analysis.

            Also provide sell and buy signals based on the analysis.
            """
            
            # Round 1
            messages = [
                    {"role": "system", "content": "You are Warren Buffet, the legendary investor."},
                    {"role": "user", "content": prompt_1},
            ]
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False
            )

            content  = response.choices[0].message.content

            # Round 2
            prompt_2 = f"""
            Provide the following:
            - What is your recommendation? Buy or Sell or Hold?
            - Buy/Sell price.
            - A risk/reward ratio based on the analysis.
            - A rating between 1 and 10 based on the analysis.
            - A summary of the analysis.

            Output in JSON format:
            EXAMPLE JSON OUTPUT:
            {{
                "suggestion_action": "Hold (with caution)",
                "suggestion_buy_price": "10.00",
                "suggestion_sell_price": "20.00",
                "suggestion_risk_reward_ratio": "1:2",
                "suggestion_rating": "8",
                "suggestion_summary": "The stock is undervalued and has strong growth potential."
            }}
            """
            messages.append({'role': 'assistant', 'content': content})
            messages.append({'role': 'user', 'content': prompt_2})
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False
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

            self.ai_suggestion = content
            self.suggestion_action = suggestion.get("suggestion_action")
            self.suggestion_buy_price = flt(suggestion.get("suggestion_buy_price"))
            self.suggestion_sell_price = flt(suggestion.get("suggestion_sell_price"))
            self.suggestion_risk_reward_ratio = suggestion.get("suggestion_risk_reward_ratio")
            self.suggestion_rating = suggestion.get("suggestion_rating")
            self.suggestion_summary = suggestion.get("suggestion_summary")
            self.save()
            return {'success': True}
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Request error: {str(e)}", "OpenWebUI API Error")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            frappe.log_error(f"Error generating AI suggestion: {str(e)}", "AI Suggestion Error")
            return {'success': False, 'error': str(e)}

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
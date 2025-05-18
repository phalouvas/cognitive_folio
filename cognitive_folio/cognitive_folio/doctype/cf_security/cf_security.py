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

            # Prepare data for the prompt
            ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
            
            news_json = json.loads(self.news) if self.news else []
            # Extract URLs from news data and format with # prefix
            news_urls = ["#" + item.get("content", {}).get("clickThroughUrl", {}).get("url", "") 
                            for item in news_json if item.get("content") and item.get("content").get("clickThroughUrl")]
            news = "\n".join(news_urls)
            
            # Create base prompt with security data
            prompt = f"""
            You own below security.

            Security: {self.security_name} ({self.symbol})
            Exchange: {self.stock_exchange}
            Sector: {self.sector}
            Industry: {self.industry}
            Current Price: {self.current_price}
            
            Evaluate below security using Warren Buffett's qualitative principles,
            but use quantitative data from "Ticker Information" to support your evaluation.
            
            Ticker Information:
            {json.dumps(ticker_info, indent=2)}
            
            For your evaluation also consider "Recent News":
            Recent News:
            {json.dumps(news, indent=2)}
            """                        
            
            # Add final instructions to the prompt
            prompt += """
            Do not mention your name.
            Include a rating from 1 to 5, where 1 is the worst and 5 is the best.
            State your recommendation Buy, Hold, or Sell.
            State the price target that you would think for buying and selling.
            Output in JSON format but give titles to each column so I am able to render them in markdown format.
            
            EXAMPLE JSON OUTPUT:
            {
                "Summary": "Analysis summary of the security. Do not mention your name.",
                "Evaluation": {
                    "Rating": 4,
                    "Recommendation": "Buy",
                    "Price Target Buy Below": 156.01,
                    "Price Target Sell Above": 185.18
                },
                "Qualitative Analysis": {
                    "Durable Competitive Advantage": {
                        "Assessment": "Strong",
                        "Supporting Data": {
                            "Market Position": "Dominant player in China's e-commerce and cloud computing with 39.95% gross margins and 13.06% profit margins.",
                            "Return on Equity": "11.44% (moderate but stable)",
                            "EBITDA Margins": "18.33% (healthy operational efficiency)"
                        }
                    },
                    "Management Competence": {
                        "Assessment": "Experienced leadership with long-term alignment",
                        "Supporting Data": {
                            "Executive Tenure": "Key officers like Joseph Tsai (Executive Chairman) and Yongming Wu (CEO) have extensive industry experience.",
                            "Compensation Risk": "Low (score 10)",
                            "Insider Ownership": "6.48% (moderate alignment with shareholders)"
                        }
                    },
                    "Valuation": {
                        "Assessment": "Undervalued relative to fundamentals",
                        "Supporting Data": {
                            "Price-to-Book": "0.28 (extremely low)",
                            "Forward P/E": "13.07 (below sector average)",
                            "Price-to-Sales": "2.36 (attractive for growth company)"
                        }
                    },
                    "Financial Health": {
                        "Assessment": "Robust balance sheet",
                        "Supporting Data": {
                            "Current Ratio": "1.55 (strong liquidity)",
                            "Debt-to-Equity": "22.78 (conservative leverage)",
                            "Operating Cash Flow": "HK$163.5B (substantial reinvestment capacity)"
                        }
                    }
                },
                "Risk Factors": {
                    "Geopolitical Risks": "U.S.-China tensions and regulatory scrutiny",
                    "Growth Sustainability": "Earnings growth rate of 296.4% may face normalization pressure",
                    "Recent Performance": "52-week price decline of -15.42% from highs reflects market concerns"
                }
            }
            """
            
            messages = [
                    {"role": "system", "content": "You are Warren Buffet, the legendary investor."},
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
        
        # Add Evaluation
        if "Evaluation" in data:
            eval_data = data["Evaluation"]
            markdown.append("## Evaluation")
            
            rating = "⭐" * int(eval_data.get("Rating", 0))
            markdown.append(f"**Rating**: {eval_data.get('Rating', 0)} {rating}")
            markdown.append(f"**Recommendation**: {eval_data.get('Recommendation', '-')}")
            markdown.append(f"**Buy Below**: {eval_data.get('Price Target Buy Below', '-')}")
            markdown.append(f"**Sell Above**: {eval_data.get('Price Target Sell Above', '-')}")
            markdown.append("")
        
        # Add Qualitative Analysis
        if "Qualitative Analysis" in data:
            markdown.append("## Qualitative Analysis")
            qual_data = data["Qualitative Analysis"]
            
            for category, details in qual_data.items():
                markdown.append(f"### {category}")
                markdown.append(f"**Assessment**: {details.get('Assessment', '-')}")
                
                if "Supporting Data" in details:
                    markdown.append("\n**Supporting Data**:")
                    for key, value in details["Supporting Data"].items():
                        markdown.append(f"- **{key}**: {value}")
                markdown.append("")
        
        # Add Risk Factors
        if "Risk Factors" in data:
            markdown.append("## Risk Factors")
            for factor, description in data["Risk Factors"].items():
                markdown.append(f"- **{factor}**: {description}")
        
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
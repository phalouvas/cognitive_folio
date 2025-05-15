# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import json
import os
import requests
from urllib.parse import urljoin
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_files_path

try:
    import yfinance as yf
    YFINANCE_INSTALLED = True
except ImportError:
    YFINANCE_INSTALLED = False

class CFSecurity(Document):
    def validate(self):
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
        else:
            frappe.throw("YFinance package is not installed. Cannot fetch current price.")

    @frappe.whitelist()
    def fetch_current_price(self):
        """Fetch the current price from Yahoo Finance"""
        try:
            ticker = yf.Ticker(self.symbol)
            ticker_info = ticker.info
            if 'regularMarketPrice' in ticker_info:
                self.ticker_info = frappe.as_json(ticker_info)
                self.currency = ticker_info['currency']
                self.country = ticker_info.get('country', '')
                self.region, self.subregion = get_country_region_from_api(self.country)
                self.isin = ticker.isin
                self.news = frappe.as_json(ticker.news)
                self.save()
        except Exception as e:
            frappe.log_error(f"Error fetching current price: {str(e)}", "Fetch Current Price Error")
            frappe.throw("Error fetching current price. Please check the symbol.")
            
    def on_update(self):
        """Update related documents when a security is updated"""
        self.update_portfolio_holdings()
            
    def update_portfolio_holdings(self):
        """Update the value of portfolio holdings that contain this security"""
        if self.has_value_changed("current_price"):
            # Check if CF Portfolio Holding DocType exists before trying to access it
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
        try:
            # Get OpenWebUI settings
            settings = frappe.get_single("CF Settings")
            url = settings.open_ai_url
            api_key = settings.get_password('open_ai_api_key')
            
            # Validate required settings
            if not url or not api_key:
                return {'success': False, 'error': _('OpenWebUI API URL or API Key not configured in CF Settings')}
            
            # Ensure URL ends with slash
            if not url.endswith('/'):
                url = url + '/'
                
            # Prepare data for the prompt
            ticker_info = json.loads(self.ticker_info) if self.ticker_info else {}
            news = json.loads(self.news) if self.news else []
            
            # Create base prompt with security data
            prompt = f"""
            Please analyze this security and provide investment insights:
            
            Security: {self.security_name} ({self.symbol})
            Exchange: {self.stock_exchange}
            Sector: {self.sector}
            Industry: {self.industry}
            
            Ticker Information:
            {json.dumps(ticker_info, indent=2)}
            
            Recent News:
            {json.dumps(news, indent=2)}
            """
            
            # Get the AI model to use
            model = settings.default_ai_model
            if not model:
                frappe.throw(_('Default AI model is not configured in CF Settings'))
            
            # Check if there are any attached files to include
            file_ids = []
            attachments = frappe.get_all("File", 
                filters={
                    "attached_to_doctype": "CF Security",
                    "attached_to_name": self.name
                },
                fields=["name", "file_name", "file_url", "is_private"]
            )
            
            # 1. Upload files if they exist
            if attachments:
                for attachment in attachments:
                    file_path = get_files_path(attachment.file_name, is_private=attachment.is_private)
                    if os.path.exists(file_path):
                        try:
                            # Upload file to OpenWebUI
                            upload_url = urljoin(url, 'api/v1/files')
                            headers = {
                                'Authorization': f'Bearer {api_key}',
                                'Content-Type': 'application/json'
                            }
                            
                            with open(file_path, 'rb') as file:
                                files = {'file': (attachment.file_name, file)}
                                upload_response = requests.post(
                                    upload_url,
                                    headers=headers,
                                    files=files
                                )
                        
                            if upload_response.status_code == 200:
                                upload_data = upload_response.json()
                                if 'id' in upload_data:
                                    file_ids.append(upload_data['id'])
                                    
                                    # Add info about the file to the prompt
                                    prompt += f"\n\nI've analyzed the attached file: {attachment.file_name}"
                        except Exception as e:
                            frappe.log_error(f"Error uploading file {attachment.file_name}: {str(e)}", 
                                              "OpenWebUI API Error")
        
            # Add final instructions to the prompt
            prompt += """
            
            Please provide:
            1. A summary of the company
            2. Key financial metrics analysis
            3. Recent news impact
            4. Potential investment outlook
            5. Risk factors
            """
            
            # 2. Create a chat completion request
            api_url = urljoin(url, 'api/chat/completions')
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            # Add file references if we have uploaded files
            if file_ids:
                payload["file_ids"] = file_ids
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # 3. Make the API call
            response = requests.post(
                api_url, 
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                response_data = response.json()
                
                # Extract the AI response - adjust based on actual response format
                if response_data.get('choices') and len(response_data['choices']) > 0:
                    message = response_data['choices'][0].get('message', {})
                    ai_response = message.get('content', '')
                    
                    if ai_response:
                        # Save the response to the ai_suggestion field
                        self.ai_suggestion = ai_response
                        self.save()
                        
                        return {'success': True}
                    else:
                        return {'success': False, 'error': _('Empty response from AI')}
                else:
                    return {'success': False, 'error': _('Unexpected response format from OpenWebUI')}
            else:
                error_message = f"HTTP Error: {response.status_code}"
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict):
                        error_message += f" - {json.dumps(error_data)}"
                    else:
                        error_message += f" - {response.text}"
                except:
                    error_message += f" - {response.text}"
                
                frappe.log_error(error_message, "OpenWebUI API Error")
                return {'success': False, 'error': error_message}
                
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

    # get country code from country
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
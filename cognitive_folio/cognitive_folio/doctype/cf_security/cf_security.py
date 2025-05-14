# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, flt
import requests

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
    def fetch_market_data(self):
        """Fetch latest market data for this security"""
        if not self.symbol:
            frappe.msgprint("Symbol/Ticker is required to fetch market data")
            return
            
        if not YFINANCE_INSTALLED:
            frappe.msgprint("YFinance package is not installed. Please run 'bench pip install yfinance'")
            return
            
        try:
            # Try to fetch data from Yahoo Finance
            ticker = yf.Ticker(self.symbol)
            ticker_info = ticker.info
            
            updated_fields = []
            
            # Update basic information if missing
            if not self.security_name and 'longName' in ticker_info:
                self.security_name = ticker_info['longName']
                updated_fields.append("security name")
            
            if not self.sector and 'sector' in ticker_info:
                self.sector = ticker_info['sector']
                updated_fields.append("sector")
                
            if not self.industry and 'industry' in ticker_info:
                self.industry = ticker_info['industry']
                updated_fields.append("industry")
                
            # Update current price
            if 'regularMarketPrice' in ticker_info:
                self.current_price = flt(ticker_info['regularMarketPrice'])
                updated_fields.append("current price")
                
            # Update stock exchange 
            if not self.stock_exchange and 'exchange' in ticker_info:
                self.stock_exchange = ticker_info['exchange']
                updated_fields.append("stock exchange")
                
            if updated_fields:
                self.save()
                frappe.msgprint(f"Updated {', '.join(updated_fields)} for {self.symbol}")
            else:
                frappe.msgprint(f"No new data found for {self.symbol}")
                
        except Exception as e:
            frappe.log_error(f"Failed to fetch market data for {self.symbol}: {str(e)}", 
                           "CF Security Data Fetch")
            frappe.msgprint(f"Error fetching data for {self.symbol}: {str(e)}")

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

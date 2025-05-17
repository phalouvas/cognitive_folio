import frappe
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.setup.utils import get_exchange_rate

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
def fetch_all_prices(portfolio_name):
    """Update prices for all holdings in this portfolio using batch requests"""
    try:
        import yfinance as yf
    except ImportError:
        frappe.msgprint("YFinance package is not installed. Please run 'bench pip install yfinance'")
        return 0
    
    portfolio = frappe.get_doc("CF Portfolio", portfolio_name)
        
    # Get all holdings for this portfolio (excluding Cash type securities)
    holdings = frappe.get_all(
        "CF Portfolio Holding",
        filters=[
            ["portfolio", "=", portfolio.name],
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
                "doc": security
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
            
            if not symbol or symbol not in tickers.tickers:
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
                        if security_currency == portfolio.currency:
                            # No conversion needed if currencies match
                            holding.current_price = price_in_security_currency
                        else:
                            # Convert price to portfolio currency
                            try:
                                conversion_rate = get_exchange_rate(security_currency, portfolio.currency)
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
import frappe
from frappe.model.document import Document
from frappe.utils import flt

class CFPortfolio(Document):
	def validate(self):
		self.validate_start_date()
		self.validate_disabled_state()
	
	def validate_start_date(self):
		"""Ensure start date is not in future"""
		if self.start_date and self.start_date > frappe.utils.today():
			frappe.throw("Start Date cannot be in the future")
	
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
	"""Update prices for all securities in this portfolio using batch requests"""
	try:
		import yfinance as yf
	except ImportError:
		frappe.msgprint("YFinance package is not installed. Please run 'bench pip install yfinance'")
		return 0
	

	portfolio = frappe.get_doc("CF Portfolio", portfolio_name)
		
	# Get all holdings for this portfolio
	holdings = frappe.get_all(
		"CF Portfolio Holding",
		filters={"portfolio": portfolio.name},
		fields=["security"]
	)
	
	# Get unique securities
	security_names = list(set(h.security for h in holdings))
	
	if not security_names:
		frappe.msgprint("No securities found in this portfolio")
		return 0
	
	# Get all securities data
	securities_data = {}
	for security_name in security_names:
		security = frappe.get_doc("CF Security", security_name)
		securities_data[security_name] = {
			"symbol": security.symbol,
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
		
		# Update each security with the batch data
		updated_count = 0
		
		for security_name, data in securities_data.items():
			symbol = data["symbol"]
			security = data["doc"]
			
			if not symbol or symbol not in tickers.tickers:
				continue
				
			ticker = tickers.tickers[symbol]
			
			try:
				# Get ticker info
				ticker_info = ticker.info
				updated_fields = []
				
				# Update basic information if available
				if 'sector' in ticker_info:
					security.sector = ticker_info['sector']
					updated_fields.append("sector")
					
				if 'industry' in ticker_info:
					security.industry = ticker_info['industry']
					updated_fields.append("industry")
					
				# Update current price
				if 'regularMarketPrice' in ticker_info:
					security.current_price = flt(ticker_info['regularMarketPrice'])
					updated_fields.append("current price")

				if 'currency' in ticker_info:
					security.currency = ticker_info['currency']
					updated_fields.append("currency")
				
				# Save ticker info
				if ticker_info:
					security.ticker_info = frappe.as_json(ticker_info)
					updated_fields.append("ticker info")
				
				# Save changes
				if updated_fields:
					security.save()
					updated_count += 1
					
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
# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def auto_fetch_portfolio_prices():
	"""
	Scheduled task to automatically fetch holdings data for portfolios with auth_fetch_prices enabled.
	Runs daily at 5:00 AM.
	"""
	try:
		# Get all portfolios with auth_fetch_prices enabled and not disabled
		portfolios = frappe.get_all(
			"CF Portfolio",
			filters=[
				["auth_fetch_prices", "=", 1],
				["disabled", "=", 0]
			],
			fields=["name", "portfolio_name"]
		)
		
		if not portfolios:
			frappe.logger().info("No portfolios found with auto fetch prices enabled")
			return
		
		total_portfolios = len(portfolios)
		updated_portfolios = 0
		
		frappe.logger().info(f"Starting auto price fetch for {total_portfolios} portfolios")
		
		for portfolio in portfolios:
			try:
				# Get the portfolio document
				portfolio_doc = frappe.get_doc("CF Portfolio", portfolio.name)
				
				# Call the fetch_holdings_data method without fundamentals
				result = portfolio_doc.fetch_holdings_data(with_fundamentals=False)
				
				if result and result > 0:
					updated_portfolios += 1
					frappe.logger().info(f"Successfully updated {result} holdings for portfolio: {portfolio.portfolio_name}")
				else:
					frappe.logger().info(f"No holdings to update for portfolio: {portfolio.portfolio_name}")
					
			except Exception as e:
				frappe.log_error(
					f"Error fetching prices for portfolio {portfolio.portfolio_name}: {str(e)}",
					"Auto Fetch Portfolio Prices Error"
				)
				continue
		
		frappe.logger().info(f"Auto price fetch completed. Updated {updated_portfolios} out of {total_portfolios} portfolios")
		
		# Commit the changes
		frappe.db.commit()
		
	except Exception as e:
		frappe.log_error(
			f"Error in auto_fetch_portfolio_prices scheduled task: {str(e)}",
			"Auto Fetch Portfolio Prices Task Error"
		)

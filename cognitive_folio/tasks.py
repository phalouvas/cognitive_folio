# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _

@frappe.whitelist()
def auto_fetch_portfolio_prices():
	"""
	Scheduled task to automatically fetch holdings data for portfolios with auth_fetch_prices enabled.
	Runs daily at 3:00 AM.
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
					
					# After successful price fetch, run news evaluation
					try:
						frappe.logger().info(f"Starting news evaluation for portfolio: {portfolio.portfolio_name}")
						portfolio_doc.evaluate_holdings_news()
						frappe.logger().info(f"News evaluation queued for portfolio: {portfolio.portfolio_name}")
					except Exception as news_error:
						frappe.log_error(
							f"Error running news evaluation for portfolio {portfolio.portfolio_name}: {str(news_error)}",
							"Auto News Evaluation Error"
						)
						# Continue with other portfolios even if news evaluation fails
						continue
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

@frappe.whitelist()
def auto_portfolio_notifications():
	"""
	Scheduled task to send notifications for portfolios with auth_fetch_prices enabled.
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
			fields=["name", "portfolio_name", "owner"]
		)
		
		if not portfolios:
			frappe.logger().info("No portfolios found with auto fetch prices enabled")
			return
		
		total_notifications = 0
		
		frappe.logger().info(f"Starting notifications for {len(portfolios)} portfolios")
		
		for portfolio in portfolios:
			try:
				# Get securities with alerts
				alert_securities = frappe.get_all(
					"CF Portfolio Holding",
					filters=[
						["portfolio", "=", portfolio.name],
						["is_alert", "=", 1]
					],
					fields=["security", "security_name", "alert_details", "current_price", "allocation_percentage"]
				)
				
				# Get securities that need evaluation
				evaluation_securities = frappe.get_all(
                    "CF Portfolio Holding",
                    filters=[
                        ["portfolio", "=", portfolio.name],
                        ["need_evaluation", "=", 1]
                    ],
                    fields=["security", "security_name", "news_reasoning", "current_price", "allocation_percentage"]
                )
				
				# Only send email if there are alerts or evaluations
				if alert_securities or evaluation_securities:
					# Get portfolio owner email
					owner_email = portfolio.owner
					if not owner_email:
						frappe.logger().warning(f"No owner found for portfolio: {portfolio.portfolio_name}")
						continue
					
					# Prepare email content
					subject = f"Portfolio Alert: {portfolio.portfolio_name}"
					
					# Build email message
					message_parts = [
						f"<h3>Daily Portfolio Alert for {portfolio.portfolio_name}</h3>",
						f"<p>Generated on {frappe.utils.now()}</p>"
					]
					
					# Add alert securities section
					if alert_securities:
						message_parts.append("<h4>🚨 Securities with Alerts</h4>")
						message_parts.append("<table border='1' style='border-collapse: collapse; width: 100%;'>")
						message_parts.append("<tr><th>Security</th><th>Current Price</th><th>Allocation %</th><th>Alert Details</th></tr>")
						
						for security in alert_securities:
							message_parts.append(f"""
								<tr>
									<td>{security.security_name or security.security}</td>
									<td>{security.current_price or 'N/A'}</td>
									<td>{security.allocation_percentage or 0:.2f}%</td>
									<td>{security.alert_details or 'No details available'}</td>
								</tr>
							""")
						message_parts.append("</table><br>")
					
					# Add evaluation securities section
					if evaluation_securities:
						message_parts.append("<h4>📊 Securities Needing Evaluation</h4>")
						message_parts.append("<table border='1' style='border-collapse: collapse; width: 100%;'>")
						message_parts.append("<tr><th>Security</th><th>Current Price</th><th>Allocation %</th><th>Recommendation</th></tr>")
						
						for security in evaluation_securities:
							message_parts.append(f"""
								<tr>
									<td>{security.security_name or security.security}</td>
									<td>{security.current_price or 'N/A'}</td>
									<td>{security.allocation_percentage or 0:.2f}%</td>
									<td>{security.news_reasoning or 'No reasoning available'}</td>
								</tr>
							""")
						message_parts.append("</table><br>")
					
					message_parts.append("<p><i>This is an automated notification from your Cognitive Folio system.</i></p>")
					
					message = "".join(message_parts)
					
					# Send email
					frappe.sendmail(
						recipients=[owner_email],
						subject=subject,
						message=message,
						header=["Portfolio Alert", "blue"]
					)
					
					total_notifications += 1
					frappe.logger().info(f"Notification sent to {owner_email} for portfolio {portfolio.portfolio_name} - Alerts: {len(alert_securities)}, Evaluations: {len(evaluation_securities)}")
				else:
					frappe.logger().info(f"No alerts or evaluations for portfolio: {portfolio.portfolio_name}")
				
			except Exception as e:
				frappe.log_error(
					f"Error sending notification for portfolio {portfolio.portfolio_name}: {str(e)}",
					"Auto Portfolio Notification Error"
				)
				continue
		
		frappe.logger().info(f"Portfolio notifications completed. Sent {total_notifications} notifications")
		
	except Exception as e:
		frappe.log_error(
			f"Error in auto_portfolio_notifications scheduled task: {str(e)}",
			"Auto Portfolio Notifications Task Error"
		)

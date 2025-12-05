# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import json
import requests
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from cognitive_folio.utils.markdown import safe_markdown_to_html
from cognitive_folio.utils.helper import replace_variables, clear_string, get_edgar_data
import re

try:
	import yfinance as yf
	YFINANCE_INSTALLED = True
except ImportError:
	YFINANCE_INSTALLED = False

class CFSecurity(Document):
	def validate(self):

		if self.security_type != "Stock" and not self.symbol:
			self.symbol = self.security_name
			
		if self.security_type == "Cash":
			self.current_price = 1.0

		if self.security_type == "Stock":
			self.validate_isin()
			self.set_news_urls()
			self.calculate_intrinsic_value()
			self.calculate_fair_value()
			self.set_alert()

	def on_change(self):
		"""Save all holdings"""
		holdings = frappe.get_all(
			"CF Portfolio Holding",
			filters={"security": self.name},
			fields=["name"]
		)
		
		for holding in holdings:
			portfolio_holding = frappe.get_doc("CF Portfolio Holding", holding.name)
			portfolio_holding.save()

	def set_news_urls(self):
		news_urls = []
		if self.news:
			try:
				news_data = json.loads(self.news)
				for item in news_data:
					if 'link' in item:
						news_urls.append(item['link'])
				self.news_html = "\n".join([url for url in news_urls])
			except json.JSONDecodeError:
				frappe.log_error("Invalid JSON format in news data", "CFSecurity News URLs")
	
	def validate_isin(self):
		"""Validate ISIN format if provided"""
		if self.isin:
			# ISIN is a 12-character alphanumeric code
			if len(self.isin) != 12:
				frappe.throw("ISIN must be 12 characters long")
			
			# Basic format validation: 2 letters country code + 9 alphanumeric + 1 check digit
			if not (self.isin[:2].isalpha() and self.isin[2:11].isalnum() and self.isin[11].isalnum()):
				frappe.throw("ISIN format is invalid. It should be 2 letters country code followed by 9 alphanumeric characters and 1 check digit")

	def on_trash(self):
		"""Delete related chats when security is deleted"""
		try:
			# Get all chats related to this security
			related_chats = frappe.get_all(
				"CF Chat",
				filters={"security": self.name},
				fields=["name"]
			)
			
			# Delete each related chat (this will also delete related CF Chat Messages due to cascade)
			for chat in related_chats:
				try:
					frappe.delete_doc("CF Chat", chat.name, force=True)
				except Exception as e:
					frappe.log_error(f"Error deleting chat {chat.name}: {str(e)}", "CF Security Chat Deletion Error")
			
		except Exception as e:
			frappe.log_error(f"Error deleting related chats for security {self.name}: {str(e)}", "CF Security On Trash Error")

	def after_insert(self):
		"""Fetch and set the current price after inserting the document"""
		if YFINANCE_INSTALLED:
			self.fetch_data(with_fundamentals=True)
			self.generate_ai_suggestion()
	
	@frappe.whitelist()
	def fetch_data(self, with_fundamentals=False):
		# Convert string to boolean if needed (frappe.call sends booleans as strings)
		if isinstance(with_fundamentals, str):
			with_fundamentals = with_fundamentals.lower() in ('true', '1', 'yes', 'on')
			
		if self.security_type != "Stock":
			return {'success': False, 'error': _('Not a stock security')}
		
		"""Fetch the current price from Yahoo Finance"""
		try:
			ticker = yf.Ticker(self.symbol)
			ticker_info = ticker.get_info()
			self.ticker_info = frappe.as_json(ticker_info)
			self.currency = ticker_info['currency']
			self.current_price = ticker_info['regularMarketPrice']
			self.news = frappe.as_json(ticker.get_news())
			self.news_urls = "\n".join([item['content']['clickThroughUrl']['url'] for item in json.loads(self.news) if item.get('content') and item['content'].get('clickThroughUrl') and item['content']['clickThroughUrl'].get('url')])
			self.country = ticker_info.get('country', '')
			if with_fundamentals:
				if self.cik:
					get_edgar_data(self.cik)
				self.profit_loss = ticker.income_stmt.to_json(date_format='iso')
				self.ttm_profit_loss = ticker.ttm_income_stmt.to_json(date_format='iso')
				self.quarterly_profit_loss = ticker.quarterly_income_stmt.to_json(date_format='iso')
				self.balance_sheet = ticker.balance_sheet.to_json(date_format='iso')
				self.quarterly_balance_sheet = ticker.quarterly_balance_sheet.to_json(date_format='iso')
				self.cash_flow = ticker.cashflow.to_json(date_format='iso')
				self.ttm_cash_flow = ticker.ttm_cashflow.to_json(date_format='iso')
				self.quarterly_cash_flow = ticker.quarterly_cashflow.to_json(date_format='iso')
				self.dividends = ticker.dividends.to_json(date_format='iso')

			if self.country == "South Korea":
				self.country = "Korea, Republic of"
			if not self.region:
				self.region, self.subregion = get_country_region_from_api(self.country)
			self.save()
	
		except Exception as e:
			frappe.log_error(f"Error fetching current price: {str(e)}", "Fetch Current Price Error")
			frappe.throw("Error fetching current price. Please check the symbol.")

	@frappe.whitelist()
	def fetch_cik(self):
		"""Fetch and set CIK using the SEC static ticker lists (single method)."""
		if self.security_type != "Stock":
			return {"success": False, "message": "CIK lookup only applies to stocks."}
		if not self.symbol:
			return {"success": False, "message": "Symbol is required to fetch CIK."}

		ticker = (self.symbol or "").upper()
		try:
			import requests
		except Exception as e:
			return {"success": False, "message": f"requests unavailable: {e}"}

		urls = [
			"https://www.sec.gov/files/company_tickers.json",
			"https://www.sec.gov/files/company_tickers_exchange.json",
		]
		headers = {
			"User-Agent": "cognitive-folio/1.0 (support@kainotomo.com)",
			"Accept": "application/json",
		}
		try:
			for url in urls:
				resp = requests.get(url, headers=headers, timeout=8)
				if resp.status_code != 200:
					continue
				try:
					data = resp.json()
				except Exception:
					continue
				# data can be dict keyed by index or a list; normalize to iterable of entries
				entries = []
				if isinstance(data, dict):
					entries = data.values()
				elif isinstance(data, list):
					entries = data
				for entry in entries:
					try:
						symbol_value = (entry.get("ticker") or "").upper()
						if symbol_value == ticker:
							cik_int = entry.get("cik_str") or entry.get("cik") or entry.get("ciknumber")
							if cik_int:
								self.cik = str(cik_int).zfill(10)
								self.save(ignore_permissions=True)
								return {"success": True, "cik": self.cik}
					except Exception:
						continue
			return {"success": False, "message": "CIK not found for this symbol from SEC list."}
		except Exception as e:
			err_msg = f"CIK lookup failed for {self.symbol}: {str(e)}"
			frappe.log_error(err_msg, "CIK Lookup Error")
			return {"success": False, "message": err_msg}

	@frappe.whitelist()
	def generate_ai_suggestion(self):
		"""Queue AI suggestion generation for the security as a background job"""
		if self.security_type != "Stock":
			return {'success': False, 'error': _('AI suggestion is only for non-stock securities')}
		
		self.ai_suggestion = "Processing your request..."
		self.ai_suggestion_html = safe_markdown_to_html(self.ai_suggestion)
		self.save()
		
		try:
			from frappe.utils.background_jobs import enqueue
			
			# Create a unique job name to prevent duplicates
			job_name = f"security_ai_suggestion_{self.name}_{frappe.utils.now()}"
			
			# Enqueue the job
			enqueue(
				method="cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.process_security_ai_suggestion",
				queue="long",
				timeout=1800,  # 30 minutes
				job_id=job_name,
				now=False,
				security_name=self.name,
				user=frappe.session.user
			)
			
			frappe.msgprint(
				_("Security AI suggestion generation has been queued. You will be notified when it's complete."),
				alert=True
			)
			
			return {'success': True, 'message': _('Security AI suggestion generation has been queued')}
		
		except Exception as e:
			frappe.log_error(f"Error queueing security AI suggestion: {str(e)}", "Security AI Suggestion Error")
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
			
			# Handle new nested rating structure
			rating_data = eval_data.get("Rating", 0)
			if isinstance(rating_data, dict):
				# New format: calculate average of all rating components
				rating_values = []
				for component, value in rating_data.items():
					try:
						rating_values.append(float(value))
					except (ValueError, TypeError):
						continue
		
				if rating_values:
					avg_rating = sum(rating_values) / len(rating_values)
					rating_value = avg_rating * 5  # Convert to 5-star scale
			
					# Add detailed breakdown
					markdown.append("### Rating Breakdown:")
					for component, value in rating_data.items():
						try:
							component_rating = float(value) * 5
							component_full_stars = int(component_rating)
							component_half_star = 1 if component_rating - component_full_stars >= 0.5 else 0
							component_stars = "⭐" * component_full_stars + "✩" * component_half_star
							markdown.append(f"- **{component}**: {component_stars} ({value})")
						except (ValueError, TypeError):
							markdown.append(f"- **{component}**: {value}")
			
					markdown.append("")
					markdown.append("### Overall Rating:")
				else:
					rating_value = 0
			else:
				# Old format: direct numeric value
				try:
					rating_value = float(rating_data) * 5
				except (ValueError, TypeError):
					rating_value = 0
	
			full_stars = int(rating_value)  # Number of full stars
			half_star = 1 if rating_value - full_stars >= 0.5 else 0  # Add half star if needed
			rating = "⭐" * full_stars + "✩" * half_star
			markdown.append(f"- **Overall Rating**: {rating} ({rating_value/5:.2f})")
			markdown.append(f"- **Recommendation**: **{eval_data.get('Recommendation', '-')}**")
			markdown.append(f"- **Buy Below**: **{self.currency} {eval_data.get('Price Target Buy Below', '-')}**")
			markdown.append(f"- **Sell Above**: **{self.currency} {eval_data.get('Price Target Sell Above', '-')}**")
			
			# Add stop loss if available
			stop_loss = eval_data.get('Price Stop Loss')
			if stop_loss and stop_loss != '-':
				markdown.append(f"- **Stop Loss**: **{self.currency} {stop_loss}**")
			
			markdown.append("")
		
		# Add Analysis
		if "Analysis" in data:
			markdown.append(f"## Analysis\n{data['Analysis']}\n")

		# Add Risks
		if "Risks" in data:
			markdown.append(f"## Risks\n{data['Risks']}\n")

		return "\n".join(markdown)

	def set_alert(self):
		"""Set alerts only for AI buy/sell signals, but provide comprehensive research details"""
		self.is_alert = 0
		self.alert_details = ""
		
		if not self.current_price or self.current_price <= 0:
			return
		
		# Get values with safe defaults
		current_price = flt(self.current_price)
		intrinsic_value = flt(self.intrinsic_value or 0)
		fair_value = flt(self.fair_value or 0)
		ai_buy_price = flt(self.suggestion_buy_price or 0)
		ai_sell_price = flt(self.suggestion_sell_price or 0)
		currency = self.currency or ""
		
		alert_messages = []
		research_summary = []
		
		# ACTIONABLE ALERTS (only these trigger is_alert = 1)
		if ai_buy_price > 0 and current_price <= ai_buy_price:
			self.is_alert = 1  # TRIGGER ALERT
			discount_pct = ((ai_buy_price - current_price) / ai_buy_price) * 100
			
			# Add confidence level based on fundamental support
			confidence_indicator = ""
			if intrinsic_value > 0:
				if current_price <= intrinsic_value * 0.85:
					confidence_indicator = " 🎯 **HIGH CONFIDENCE** (Fundamental support)"
				elif current_price <= intrinsic_value * 1.1:
					confidence_indicator = " ⚖️ **MEDIUM CONFIDENCE** (Fair fundamental value)"
				else:
					confidence_indicator = " ⚠️ **LOW CONFIDENCE** (Above fundamental value)"
			
			alert_messages.append(f"🟢 **AI BUY SIGNAL**: Current price {currency} {current_price:.2f} is {discount_pct:.1f}% below AI buy target of {currency} {ai_buy_price:.2f}{confidence_indicator}")
		
		if ai_sell_price > 0 and current_price >= ai_sell_price:
			self.is_alert = 1  # TRIGGER ALERT
			premium_pct = ((current_price - ai_sell_price) / ai_sell_price) * 100
			
			# Add confidence level based on fundamental support
			confidence_indicator = ""
			if intrinsic_value > 0:
				if current_price >= intrinsic_value * 1.2:
					confidence_indicator = " 🎯 **HIGH CONFIDENCE** (Above fundamental value)"
				elif current_price >= intrinsic_value * 0.9:
					confidence_indicator = " ⚖️ **MEDIUM CONFIDENCE** (Near fundamental value)"
				else:
					confidence_indicator = " ⚠️ **LOW CONFIDENCE** (Below fundamental value)"
			
			alert_messages.append(f"🔴 **AI SELL SIGNAL**: Current price {currency} {current_price:.2f} is {premium_pct:.1f}% above AI sell target of {currency} {ai_sell_price:.2f}{confidence_indicator}")
		
		# RESEARCH INFORMATION (always shown, never triggers alerts)
		
		# AI Target Analysis
		if ai_buy_price > 0:
			buy_variance = ((current_price - ai_buy_price) / ai_buy_price) * 100
			if buy_variance <= -5:
				research_summary.append(f"📊 At {-buy_variance:.1f}% discount to AI buy target ({currency} {ai_buy_price:.2f})")
			elif buy_variance >= 5:
				research_summary.append(f"📊 At {buy_variance:.1f}% premium to AI buy target ({currency} {ai_buy_price:.2f})")
			else:
				research_summary.append(f"📊 Near AI buy target ({currency} {ai_buy_price:.2f})")
		
		if ai_sell_price > 0:
			sell_variance = ((current_price - ai_sell_price) / ai_sell_price) * 100
			if sell_variance >= 5:
				research_summary.append(f"📊 At {sell_variance:.1f}% above AI sell target ({currency} {ai_sell_price:.2f})")
			elif sell_variance <= -5:
				research_summary.append(f"📊 At {-sell_variance:.1f}% below AI sell target ({currency} {ai_sell_price:.2f})")
			else:
				research_summary.append(f"📊 Near AI sell target ({currency} {ai_sell_price:.2f})")
		
		# Fundamental Analysis Research
		if intrinsic_value > 0:
			intrinsic_ratio = current_price / intrinsic_value
			iv_variance = ((current_price - intrinsic_value) / intrinsic_value) * 100
			
			if intrinsic_ratio <= 0.6:  # Extreme undervaluation
				discount_pct = ((intrinsic_value - current_price) / intrinsic_value) * 100
				research_summary.append(f"💎 **EXTREME UNDERVALUATION**: {discount_pct:.1f}% below intrinsic value ({currency} {intrinsic_value:.2f}) - Consider manual review")
			elif intrinsic_ratio >= 2.0:  # Extreme overvaluation
				premium_pct = ((current_price - intrinsic_value) / intrinsic_value) * 100
				research_summary.append(f"🚨 **EXTREME OVERVALUATION**: {premium_pct:.1f}% above intrinsic value ({currency} {intrinsic_value:.2f}) - Consider manual review")
			elif abs(iv_variance) <= 15:
				research_summary.append(f"📈 Fairly valued vs intrinsic value ({currency} {intrinsic_value:.2f}, {iv_variance:+.1f}%)")
			elif iv_variance < -15:
				research_summary.append(f"📈 Below intrinsic value ({currency} {intrinsic_value:.2f}, {iv_variance:+.1f}%)")
			else:
				research_summary.append(f"📈 Above intrinsic value ({currency} {intrinsic_value:.2f}, {iv_variance:+.1f}%)")
		
		if fair_value > 0:
			fv_variance = ((current_price - fair_value) / fair_value) * 100
			if abs(fv_variance) <= 10:
				research_summary.append(f"🎯 Near fair value ({currency} {fair_value:.2f}, {fv_variance:+.1f}%)")
			elif fv_variance < -10:
				research_summary.append(f"🎯 Below fair value ({currency} {fair_value:.2f}, {fv_variance:+.1f}%)")
			else:
				research_summary.append(f"🎯 Above fair value ({currency} {fair_value:.2f}, {fv_variance:+.1f}%)")
		
		# Combine alerts and research into alert_details
		all_details = []
		
		if alert_messages:
			all_details.extend(alert_messages)
			all_details.append("---")  # Separator
		
		if research_summary:
			all_details.extend(research_summary)
		else:
			all_details.append(f"📊 Current price: {currency} {current_price:.2f} (No analysis data available)")
		
		self.alert_details = "\n".join(all_details)
	
	def _set_research_summary(self, current_price, intrinsic_value, fair_value, ai_buy_price, ai_sell_price, currency):
		"""Provide non-alerting research summary for informational purposes"""
		summary_lines = []
		
		# Price vs AI targets (informational)
		if ai_buy_price > 0:
			buy_variance = ((current_price - ai_buy_price) / ai_buy_price) * 100
			if buy_variance <= -5:
				summary_lines.append(f"📊 At {-buy_variance:.1f}% discount to AI buy target ({currency} {ai_buy_price:.2f})")
			elif buy_variance >= 5:
				summary_lines.append(f"📊 At {buy_variance:.1f}% premium to AI buy target ({currency} {ai_buy_price:.2f})")
			else:
				summary_lines.append(f"📊 Near AI buy target ({currency} {ai_buy_price:.2f})")
		
		if ai_sell_price > 0:
			sell_variance = ((current_price - ai_sell_price) / ai_sell_price) * 100
			if sell_variance >= 5:
				summary_lines.append(f"📊 At {sell_variance:.1f}% above AI sell target ({currency} {ai_sell_price:.2f})")
			elif sell_variance <= -5:
				summary_lines.append(f"📊 At {-sell_variance:.1f}% below AI sell target ({currency} {ai_sell_price:.2f})")
			else:
				summary_lines.append(f"📊 Near AI sell target ({currency} {ai_sell_price:.2f})")
		
		# Fundamental analysis summary (informational)
		if intrinsic_value > 0:
			iv_variance = ((current_price - intrinsic_value) / intrinsic_value) * 100
			if abs(iv_variance) <= 15:
				summary_lines.append(f"📈 Fairly valued vs intrinsic value ({currency} {intrinsic_value:.2f}, {iv_variance:+.1f}%)")
			elif iv_variance < -15:
				summary_lines.append(f"📈 Below intrinsic value ({currency} {intrinsic_value:.2f}, {iv_variance:+.1f}%)")
			else:
				summary_lines.append(f"📈 Above intrinsic value ({currency} {intrinsic_value:.2f}, {iv_variance:+.1f}%)")
		
		if fair_value > 0:
			fv_variance = ((current_price - fair_value) / fair_value) * 100
			if abs(fv_variance) <= 10:
				summary_lines.append(f"🎯 Near fair value ({currency} {fair_value:.2f}, {fv_variance:+.1f}%)")
			elif fv_variance < -10:
				summary_lines.append(f"🎯 Below fair value ({currency} {fair_value:.2f}, {fv_variance:+.1f}%)")
			else:
				summary_lines.append(f"🎯 Above fair value ({currency} {fair_value:.2f}, {fv_variance:+.1f}%)")
		
		# Set summary or default message
		if summary_lines:
			self.alert_details = " | ".join(summary_lines)
		else:
			self.alert_details = f"📊 Current price: {currency} {current_price:.2f} (No analysis data available)"

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

	def _get_current_risk_free_rate(self):
		"""Get current risk-free rate from cached treasury securities"""
		try:
			# Try to get treasury security for this security's country
			country_treasury = frappe.get_list("CF Security", 
				filters={
					"security_type": "Treasury Rate",
					"country": self.country
				},
				fields=["name", "current_price"],
				limit=1
			)
			
			if country_treasury and country_treasury[0].get('current_price'):
				# Convert percentage to decimal (stored as percentage)
				risk_free_rate = country_treasury[0]['current_price'] / 100
				
				# Apply country risk premium for non-major economies
				if self.country not in ['United States', 'Germany', 'United Kingdom', 'Japan', 'Canada']:
					country_risk_premium = 0.005  # Add 0.5% country risk premium
					risk_free_rate += country_risk_premium
				
				return risk_free_rate
			
			# If no treasury security found, use fallback rates directly
			raise Exception(f"No treasury security found for {self.country}")
			
		except Exception as e:
			
			# Fallback to reasonable estimates by country
			fallback_rates = {
				'United States': 0.045,
				'Germany': 0.025,
				'United Kingdom': 0.040,
				'Japan': 0.015,
				'Canada': 0.040,
				'Australia': 0.042,
				'France': 0.028,
				'Switzerland': 0.018,
				'Netherlands': 0.025,
				'Sweden': 0.020,
				'Norway': 0.025,
				'Denmark': 0.022,
				'South Korea': 0.030,
				'Taiwan': 0.025,
				'Hong Kong': 0.035,
				'Singapore': 0.030,
				'China': 0.035,
				'India': 0.065,
				'Brazil': 0.085,
				'Mexico': 0.075,
				'South Africa': 0.080,
			}
			
			return fallback_rates.get(self.country, 0.050)  # Default 5% for unknown countries
	
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
			risk_free_rate = self._get_current_risk_free_rate()
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
						pass
						#frappe.log_error(f"DCF value {per_share_value} seems unreasonable vs current price {current_price} (ratio: {price_ratio})", "DCF Sanity Check Warning")
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
	
@frappe.whitelist()
def process_security_ai_suggestion(security_name, user):
	"""Process AI suggestion for the security (meant to be run as a background job)"""
	try:

		# Get the security document
		security = frappe.get_doc("CF Security", security_name)
		
		if security.security_type == "Cash":
			return False
		
		try:
			from openai import OpenAI            
		except ImportError:
			frappe.log_error("OpenAI package is not installed. Please run 'bench pip install openai'", "AI Suggestion Error")
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'security_id': security_name,
					'status': 'error',
					'error': 'OpenAI package is not installed',
					'message': 'Please run "bench pip install openai" to install the required package.'
				},
				user=user
			)
			return False
		
		try:
			# Get OpenWebUI settings
			settings = frappe.get_single("CF Settings")
			client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
			model = settings.default_ai_model
			if not model:
				raise ValueError(_('Default AI model is not configured in CF Settings'))

			prompt = security.ai_prompt or ""

			# Update regex to handle more complex paths including array indices
			prompt = re.sub(r'\{\{([\w\.]+)\}\}', lambda match: replace_variables(match, security), prompt)
			
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
			
			# Check if response has choices and content
			if not response.choices or not response.choices[0].message.content:
				raise ValueError("Empty response received from AI model")
			
			content_string = response.choices[0].message.content.strip()
			
			# Validate that we got actual content
			if not content_string:
				raise ValueError("No content in AI response")
			
		except Exception as api_error:
			error_message = f"AI API error: {str(api_error)}"
			frappe.log_error(error_message, "OpenAI API Error")
			
			# Update security with error status
			security.reload()
			security.ai_suggestion = f"❌ **Error generating AI analysis**: {str(api_error)}\n\nPlease try again later or check the AI service configuration."
			security.ai_suggestion_html = safe_markdown_to_html(security.ai_suggestion)
			security.flags.ignore_version = True
			security.flags.ignore_mandatory = True
			security.save()
			
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'security_id': security_name,
					'status': 'error',
					'error': error_message,
					'message': error_message
				},
				user=user
			)
			
			return False

		try:
			content_string = clear_string(content_string)
			suggestion = json.loads(content_string)

			# Validate the JSON structure
			if not isinstance(suggestion, dict):
				raise ValueError("AI response is not a valid JSON object")

		except json.JSONDecodeError as json_error:
			# If JSON parsing still fails, try a more robust cleanup approach
			try:
				# Remove markdown formatting and fix common JSON issues
				cleaned = content_string.strip()
				
				# Find all string values in the JSON and clean them
				def clean_json_string(match):
					string_content = match.group(1)
					# Replace literal newlines with \n
					string_content = string_content.replace('\n', '\\n')
					# Replace other problematic characters
					string_content = string_content.replace('\r', '\\r')
					string_content = string_content.replace('\t', '\\t')
					string_content = string_content.replace('&nbsp;', ' ')
					# Handle unescaped quotes within strings
					string_content = re.sub(r'(?<!\\)"', '\\"', string_content)
					return f'"{string_content}"'
				
				# Apply cleaning to all JSON string values
				cleaned = re.sub(r'"([^"]*(?:\\.[^"]*)*)"', clean_json_string, cleaned, flags=re.DOTALL)
				
				suggestion = json.loads(cleaned)
				
			except (json.JSONDecodeError, Exception) as secondary_error:
				error_message = f"Invalid JSON in AI response: {str(json_error)}"
				frappe.log_error(f"{error_message}\nRaw response: {content_string}", "AI JSON Parse Error")
				
				# Fallback: save the raw response as markdown
				security.reload()
				security.ai_suggestion = f"⚠️ **AI Analysis** (Raw Response)\n\n{content_string}"
				security.ai_suggestion_html = safe_markdown_to_html(security.ai_suggestion)
				security.flags.ignore_version = True
				security.flags.ignore_mandatory = True
				security.save()
				
				# Notify user of partial success
				frappe.publish_realtime(
					event='cf_job_completed',
					message={
						'security_id': security_name,
						'status': 'error',
						'error': 'AI response format issue - raw response saved',
						'message': 'AI response had formatting issues but content was saved'
					},
					user=user
				)
				
				return True  # Still consider it a success since we got some response

		except Exception as parse_error:
			error_message = f"Error parsing AI response: {str(parse_error)}"
			frappe.log_error("AI Response Parse Error", error_message)
			
			# Update security with error status
			security.reload()
			security.ai_suggestion = f"❌ **Error processing AI response**: {str(parse_error)}\n\nRaw response saved for debugging."
			security.ai_suggestion_html = safe_markdown_to_html(security.ai_suggestion)
			security.flags.ignore_version = True
			security.flags.ignore_mandatory = True
			security.save()
			
			# Notify user of failure
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'security_id': security_name,
					'status': 'error',
					'error': error_message,
					'message': error_message
				},
				user=user
			)
			
			return False
	
		# Validate the JSON structure has expected fields
		required_sections = ["Evaluation"]
		missing_sections = [section for section in required_sections if section not in suggestion]

		if missing_sections:
			frappe.log_error(f"AI response missing required sections: {missing_sections}", "AI Response Validation Warning")
			# Continue processing with available data

		# Convert JSON to markdown for better display
		markdown_content = security.convert_json_to_markdown(suggestion)

		# Reload the document to get the latest version and avoid modification conflicts
		security.reload()

		# Safely extract values with defaults
		evaluation = suggestion.get("Evaluation", {})
		security.ai_response = content_string
		security.suggestion_action = evaluation.get("Recommendation", "")
		
		# Handle new nested rating structure
		rating_data = evaluation.get("Rating", 0)
		if isinstance(rating_data, dict):
			# New format: extract individual ratings and calculate overall
			security.rating_moat = float(rating_data.get("Moat", 0))
			security.rating_management = float(rating_data.get("Management", 0))
			security.rating_financials = float(rating_data.get("Financials", 0))
			security.rating_valuation = float(rating_data.get("Valuation", 0))
			security.rating_industry = float(rating_data.get("Industry", 0))
			
			# Calculate overall rating as average of all components
			rating_values = []
			for component in ["Moat", "Management", "Financials", "Valuation", "Industry"]:
				value = rating_data.get(component)
				if value is not None:
					try:
						rating_values.append(float(value))
					except (ValueError, TypeError):
						continue
			
			if rating_values:
				security.suggestion_rating = sum(rating_values) / len(rating_values)
			else:
				security.suggestion_rating = 0
		else:
			# Old format: direct numeric value
			try:
				security.suggestion_rating = float(rating_data)
				# Clear individual ratings if using old format
				security.rating_moat = 0
				security.rating_management = 0
				security.rating_financials = 0
				security.rating_valuation = 0
				security.rating_industry = 0
			except (ValueError, TypeError):
				security.suggestion_rating = 0
		
		security.suggestion_buy_price = evaluation.get("Price Target Buy Below", 0)
		security.suggestion_sell_price = evaluation.get("Price Target Sell Above", 0)
		security.evaluation_stop_loss = evaluation.get("Price Stop Loss", 0)
		security.ai_suggestion = markdown_content
		security.ai_suggestion_html = safe_markdown_to_html(markdown_content)
		security.news_reasoning = None
		security.need_evaluation = False
		security.ai_modified = frappe.utils.now()
		
		# Use flags to ignore timestamp validation and force save
		security.flags.ignore_version = True
		security.flags.ignore_mandatory = True
		security.save()
		
		# Create CF Chat and CF Chat Message
		chat_doc = frappe.new_doc("CF Chat")
		chat_doc.security = security_name
		chat_doc.title = f"AI Analysis for {security.security_name or security.symbol} @ {frappe.utils.today()}"
		chat_doc.system_prompt = settings.system_content
		chat_doc.save()
		
		# Create the chat message
		message_doc = frappe.new_doc("CF Chat Message")
		message_doc.chat = chat_doc.name
		message_doc.prompt = prompt
		message_doc.response = markdown_content
		message_doc.response_html = safe_markdown_to_html(message_doc.response)
		message_doc.model = model
		message_doc.status = "Success"
		message_doc.system_prompt = settings.system_content
		message_doc.tokens = response.usage.to_json() if hasattr(response, 'usage') else None
		message_doc.flags.ignore_before_save = True
		message_doc.save()
		
		frappe.db.commit()  # Single commit for all changes
		
		# Notify the user that the analysis is complete
		frappe.publish_realtime(
			event='cf_job_completed',
			message={
				'security_id': security_name,
				'status': 'success',
				'chat_id': chat_doc.name,
				'message': f"AI analysis completed for {security.security_name or security.symbol}.",
			},
			user=user
		)
		
		return True
			
	except requests.exceptions.RequestException as e:
		error_message = f"Request error: {str(e)}"
		frappe.log_error("OpenWebUI API Error", error_message)
		
		# Notify user of failure
		frappe.publish_realtime(
			event='cf_job_completed',
			message={
				'security_id': security_name,
				'status': 'error',
				'error': error_message,
				'message': error_message
			},
			user=user
		)
		
		return False
		
	except Exception as e:
		error_message = f"Error generating AI suggestion: {str(e)}"
		
		# Create a short, descriptive title for the error log
		short_title = f"AI Suggestion Error - {security_name}"
		if len(short_title) > 140:
			short_title = f"AI Suggestion Error"[:140]
		
		# FIXED: Correct parameter order - title first, then message
		frappe.log_error(short_title, error_message)
		
		# Notify user of failure
		frappe.publish_realtime(
			event='cf_job_completed',
			message={
				'security_id': security_name,
				'status': 'error',
				'error': error_message[:200],  # Truncate for realtime message too
				'message': error_message[:200]
			},
			user=user
		)
		
		return False
	
@frappe.whitelist()
def fetch_data_selected(docnames, with_fundamentals=False):
	"""Fetch latest data for selected securities"""
	if isinstance(docnames, str):
		docnames = [d.strip() for d in docnames.strip("[]").replace('"', '').split(",")]
	
	# Convert string to boolean if needed (frappe.call sends booleans as strings)
	if isinstance(with_fundamentals, str):
		with_fundamentals = with_fundamentals.lower() in ('true', '1', 'yes', 'on')
	
	if not docnames:
		frappe.throw(_("Please select at least one Batch"))
	
	total_steps = len(docnames)
	for counter, docname in enumerate(docnames, 1):
		security = frappe.get_doc("CF Security", docname)
		frappe.publish_progress(
			percent=(counter)/total_steps * 100,
			title="Processing",
			description=f"Processing item {counter} of {total_steps} ({security.security_name or security.symbol})",
		)
		security.fetch_data(with_fundamentals=with_fundamentals)
		
	return total_steps

@frappe.whitelist()
def generate_ai_suggestion_selected(docnames):
	"""Fetch latest data for selected securities"""
	if isinstance(docnames, str):
		docnames = [d.strip() for d in docnames.strip("[]").replace('"', '').split(",")]

	if not docnames:
		frappe.throw(_("Please select at least one Batch"))
	
	total_steps = len(docnames)
	for counter, docname in enumerate(docnames, 1):
		security = frappe.get_doc("CF Security", docname)
		frappe.publish_progress(
			percent=(counter)/total_steps * 100,
			title="Processing",
			description=f"Processing item {counter} of {total_steps} ({security.security_name or security.symbol})",
		)
		security.generate_ai_suggestion()
		
	return total_steps

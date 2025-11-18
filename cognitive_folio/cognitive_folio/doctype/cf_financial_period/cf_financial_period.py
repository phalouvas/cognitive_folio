# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class CFFinancialPeriod(Document):
	def validate(self):
		"""Validate and compute derived metrics"""
		self.compute_margins()
		self.compute_ratios()
		self.set_data_quality_score()
	
	def set_data_quality_score(self):
		"""Calculate data quality score based on source"""
		quality_scores = {
			"Manual Entry": 100,
			"PDF Upload": 95,
			"SEC Edgar": 90,
			"Yahoo Finance": 85,
			"Other API": 70
		}
		self.data_quality_score = quality_scores.get(self.data_source, 50)
	
	def compute_margins(self):
		"""Compute margin percentages (stored as decimals, e.g., 0.6882 for 68.82%)"""
		if self.total_revenue and self.total_revenue != 0:
			if self.gross_profit:
				self.gross_margin = self.gross_profit / self.total_revenue
			if self.operating_income:
				self.operating_margin = self.operating_income / self.total_revenue
			if self.net_income:
				self.net_margin = self.net_income / self.total_revenue
	
	def compute_ratios(self):
		"""Compute financial ratios (stored as decimals, e.g., 0.15 for 15%)"""
		# ROE
		if self.shareholders_equity and self.shareholders_equity != 0 and self.net_income:
			self.roe = self.net_income / self.shareholders_equity
		
		# ROA
		if self.total_assets and self.total_assets != 0 and self.net_income:
			self.roa = self.net_income / self.total_assets
		
		# Debt to Equity
		if self.shareholders_equity and self.shareholders_equity != 0 and self.total_debt:
			self.debt_to_equity = self.total_debt / self.shareholders_equity
		
		# Current Ratio
		if self.current_liabilities and self.current_liabilities != 0 and self.current_assets:
			self.current_ratio = self.current_assets / self.current_liabilities
		
		# Quick Ratio (Current Assets - Inventory) / Current Liabilities
		if self.current_liabilities and self.current_liabilities != 0 and self.current_assets:
			inventory = self.inventory or 0
			self.quick_ratio = (self.current_assets - inventory) / self.current_liabilities
		
		# Asset Turnover
		if self.total_assets and self.total_assets != 0 and self.total_revenue:
			self.asset_turnover = self.total_revenue / self.total_assets
	
	def after_insert(self):
		"""After inserting, calculate YoY growth if previous period exists"""
		self.calculate_growth_metrics()
	
	def on_update(self):
		"""After updating, recalculate YoY growth"""
		self.calculate_growth_metrics()
	
	def calculate_growth_metrics(self):
		"""Calculate year-over-year growth metrics"""
		# Find the previous period (same period type, 1 year ago)
		prev_year = self.fiscal_year - 1
		
		prev_period = frappe.db.get_value(
			"CF Financial Period",
			{
				"security": self.security,
				"period_type": self.period_type,
				"fiscal_year": prev_year,
				"fiscal_quarter": self.fiscal_quarter if self.period_type == "Quarterly" else ""
			},
			[
				"total_revenue",
				"net_income",
				"diluted_eps",
				"free_cash_flow",
				"operating_cash_flow"
			],
			as_dict=True
		)
		
		if prev_period:
			# Revenue Growth (stored as decimal, e.g., 0.1493 for 14.93%)
			if prev_period.total_revenue and prev_period.total_revenue != 0 and self.total_revenue:
				self.revenue_growth_yoy = (self.total_revenue - prev_period.total_revenue) / prev_period.total_revenue
			
			# Net Income Growth
			if prev_period.net_income and prev_period.net_income != 0 and self.net_income:
				self.net_income_growth_yoy = (self.net_income - prev_period.net_income) / prev_period.net_income
			
			# EPS Growth
			if prev_period.diluted_eps and prev_period.diluted_eps != 0 and self.diluted_eps:
				self.eps_growth_yoy = (self.diluted_eps - prev_period.diluted_eps) / prev_period.diluted_eps
			
			# FCF Growth
			if prev_period.free_cash_flow and prev_period.free_cash_flow != 0 and self.free_cash_flow:
				self.fcf_growth_yoy = (self.free_cash_flow - prev_period.free_cash_flow) / prev_period.free_cash_flow
			
			# Operating Cash Flow Growth
			if prev_period.operating_cash_flow and prev_period.operating_cash_flow != 0 and self.operating_cash_flow:
				self.operating_cash_flow_growth_yoy = (self.operating_cash_flow - prev_period.operating_cash_flow) / prev_period.operating_cash_flow
			
			# Update without triggering recursion
			self.db_update()


def get_source_priority(source):
	"""Get priority score for data source (higher = more trusted)"""
	priorities = {
		"Manual Entry": 100,
		"PDF Upload": 95,
		"SEC Edgar": 90,
		"Yahoo Finance": 85,
		"Other API": 70
	}
	return priorities.get(source, 50)


@frappe.whitelist()
def check_import_conflicts(security_name):
	"""Check for existing periods before Yahoo import"""
	conflicts = []
	
	# Get existing periods for this security
	existing_periods = frappe.get_all(
		"CF Financial Period",
		filters={"security": security_name},
		fields=["name", "fiscal_year", "fiscal_quarter", "period_type", "data_source", "override_yahoo", "data_quality_score"],
		order_by="period_end_date DESC"
	)
	
	for period in existing_periods:
		# Check if it's higher priority than Yahoo
		if get_source_priority(period.data_source) > get_source_priority("Yahoo Finance"):
			conflicts.append({
				"period": period.name,
				"fiscal_year": period.fiscal_year,
				"fiscal_quarter": period.fiscal_quarter,
				"period_type": period.period_type,
				"source": period.data_source,
				"quality_score": period.data_quality_score,
				"override_set": period.override_yahoo
			})
	
	return conflicts


@frappe.whitelist()
def import_from_yahoo_finance(security_name, replace_existing=False, respect_override=True):
	"""Import financial data from existing Yahoo Finance JSON blobs into structured periods
	
	Args:
		security_name: Name of CF Security
		replace_existing: If True, replace ALL existing periods
		respect_override: If True, skip periods with override_yahoo=1
	"""
	import json
	from datetime import datetime
	
	security = frappe.get_doc("CF Security", security_name)
	
	imported_count = 0
	updated_count = 0
	skipped_count = 0
	errors = []
	
	# Map Yahoo Finance field names to our structure
	field_mapping = {
		# Income Statement
		"Total Revenue": "total_revenue",
		"Cost Of Revenue": "cost_of_revenue",
		"Gross Profit": "gross_profit",
		"Operating Expense": "operating_expenses",
		"Operating Income": "operating_income",
		"EBIT": "ebit",
		"EBITDA": "ebitda",
		"Interest Expense": "interest_expense",
		"Pretax Income": "pretax_income",
		"Tax Provision": "tax_provision",
		"Net Income": "net_income",
		"Diluted EPS": "diluted_eps",
		"Basic EPS": "basic_eps",
		# Balance Sheet
		"Total Assets": "total_assets",
		"Current Assets": "current_assets",
		"Cash And Cash Equivalents": "cash_and_equivalents",
		"Accounts Receivable": "accounts_receivable",
		"Inventory": "inventory",
		"Total Liabilities Net Minority Interest": "total_liabilities",
		"Current Liabilities": "current_liabilities",
		"Total Debt": "total_debt",
		"Long Term Debt": "long_term_debt",
		"Stockholders Equity": "shareholders_equity",
		"Retained Earnings": "retained_earnings",
		# Cash Flow
		"Operating Cash Flow": "operating_cash_flow",
		"Capital Expenditure": "capital_expenditures",
		"Free Cash Flow": "free_cash_flow",
		"Investing Cash Flow": "investing_cash_flow",
		"Financing Cash Flow": "financing_cash_flow",
		"Cash Dividends Paid": "dividends_paid",
	}
	
	try:
		# Import Annual Data
		if security.profit_loss:
			profit_loss_data = json.loads(security.profit_loss)
			balance_sheet_data = json.loads(security.balance_sheet) if security.balance_sheet else {}
			cash_flow_data = json.loads(security.cash_flow) if security.cash_flow else {}
			
			for date_str, pl_data in profit_loss_data.items():
				try:
					period_end_date = datetime.fromisoformat(date_str.replace('T00:00:00.000', ''))
					fiscal_year = period_end_date.year
					
					# Check if period already exists
					existing_name = frappe.db.get_value(
						"CF Financial Period",
						{
							"security": security_name,
							"period_type": "Annual",
							"fiscal_year": fiscal_year
						},
						["name", "data_source", "override_yahoo", "data_quality_score"],
						as_dict=True
					)
					
					if existing_name:
						# Apply conflict resolution logic
						if respect_override and existing_name.override_yahoo:
							skipped_count += 1
							continue  # Skip if override is set
						
						if not replace_existing:
							# Check data quality priority
							existing_priority = get_source_priority(existing_name.data_source)
							yahoo_priority = get_source_priority("Yahoo Finance")
							
							if existing_priority > yahoo_priority:
								skipped_count += 1
								continue  # Skip if existing source is higher quality
						
						# Update existing period
						period = frappe.get_doc("CF Financial Period", existing_name.name)
						is_update = True
					else:
						# Create new period
						period = frappe.new_doc("CF Financial Period")
						period.security = security_name
						period.period_type = "Annual"
						period.fiscal_year = fiscal_year
						period.period_end_date = period_end_date.date()
						period.currency = security.currency
						period.data_source = "Yahoo Finance"
						is_update = False
					
					# Get ticker info for shares outstanding
					if security.ticker_info:
						ticker_info = json.loads(security.ticker_info)
						period.shares_outstanding = ticker_info.get('sharesOutstanding')
					
					# Map income statement fields
					for yf_field, our_field in field_mapping.items():
						if yf_field in pl_data and pl_data[yf_field] is not None:
							setattr(period, our_field, pl_data[yf_field])
					
					# Map balance sheet fields
					if date_str in balance_sheet_data:
						bs_data = balance_sheet_data[date_str]
						for yf_field, our_field in field_mapping.items():
							if yf_field in bs_data and bs_data[yf_field] is not None:
								setattr(period, our_field, bs_data[yf_field])
					
					# Map cash flow fields
					if date_str in cash_flow_data:
						cf_data = cash_flow_data[date_str]
						for yf_field, our_field in field_mapping.items():
							if yf_field in cf_data and cf_data[yf_field] is not None:
								setattr(period, our_field, cf_data[yf_field])
					
					# Store raw data for reference
					period.raw_income_statement = json.dumps(pl_data, indent=2)
					if date_str in balance_sheet_data:
						period.raw_balance_sheet = json.dumps(balance_sheet_data[date_str], indent=2)
					if date_str in cash_flow_data:
						period.raw_cash_flow = json.dumps(cash_flow_data[date_str], indent=2)
					
					if is_update:
						period.save()
						updated_count += 1
					else:
						period.insert()
						imported_count += 1
					
				except Exception as e:
					errors.append(f"Error importing period {date_str}: {str(e)}")
					frappe.log_error(f"Error importing period {date_str}: {str(e)}", "Financial Period Import")
		
		# Import Quarterly Data
		if security.quarterly_profit_loss:
			profit_loss_data = json.loads(security.quarterly_profit_loss)
			balance_sheet_data = json.loads(security.quarterly_balance_sheet) if security.quarterly_balance_sheet else {}
			cash_flow_data = json.loads(security.quarterly_cash_flow) if security.quarterly_cash_flow else {}
			
			for date_str, pl_data in profit_loss_data.items():
				try:
					period_end_date = datetime.fromisoformat(date_str.replace('T00:00:00.000', ''))
					fiscal_year = period_end_date.year
					quarter = f"Q{((period_end_date.month - 1) // 3) + 1}"
					
					# Check if period already exists
					existing_name = frappe.db.get_value(
						"CF Financial Period",
						{
							"security": security_name,
							"period_type": "Quarterly",
							"fiscal_year": fiscal_year,
							"fiscal_quarter": quarter
						},
						["name", "data_source", "override_yahoo", "data_quality_score"],
						as_dict=True
					)
					
					if existing_name:
						# Apply conflict resolution logic
						if respect_override and existing_name.override_yahoo:
							skipped_count += 1
							continue
						
						if not replace_existing:
							existing_priority = get_source_priority(existing_name.data_source)
							yahoo_priority = get_source_priority("Yahoo Finance")
							
							if existing_priority > yahoo_priority:
								skipped_count += 1
								continue
						
						# Update existing period
						period = frappe.get_doc("CF Financial Period", existing_name.name)
						is_update = True
					else:
						# Create new period
						period = frappe.new_doc("CF Financial Period")
						period.security = security_name
						period.period_type = "Quarterly"
						period.fiscal_year = fiscal_year
						period.fiscal_quarter = quarter
						period.period_end_date = period_end_date.date()
						period.currency = security.currency
						period.data_source = "Yahoo Finance"
						is_update = False
					
					if security.ticker_info:
						ticker_info = json.loads(security.ticker_info)
						period.shares_outstanding = ticker_info.get('sharesOutstanding')
					
					# Map fields (same as annual)
					for yf_field, our_field in field_mapping.items():
						if yf_field in pl_data and pl_data[yf_field] is not None:
							setattr(period, our_field, pl_data[yf_field])
					
					if date_str in balance_sheet_data:
						bs_data = balance_sheet_data[date_str]
						for yf_field, our_field in field_mapping.items():
							if yf_field in bs_data and bs_data[yf_field] is not None:
								setattr(period, our_field, bs_data[yf_field])
					
					if date_str in cash_flow_data:
						cf_data = cash_flow_data[date_str]
						for yf_field, our_field in field_mapping.items():
							if yf_field in cf_data and cf_data[yf_field] is not None:
								setattr(period, our_field, cf_data[yf_field])
					
					period.raw_income_statement = json.dumps(pl_data, indent=2)
					if date_str in balance_sheet_data:
						period.raw_balance_sheet = json.dumps(balance_sheet_data[date_str], indent=2)
					if date_str in cash_flow_data:
						period.raw_cash_flow = json.dumps(cash_flow_data[date_str], indent=2)
					
					if is_update:
						period.save()
						updated_count += 1
					else:
						period.insert()
						imported_count += 1
					
				except Exception as e:
					errors.append(f"Error importing quarterly period {date_str}: {str(e)}")
					frappe.log_error(f"Error importing quarterly period {date_str}: {str(e)}", "Financial Period Import")
		
		# Commit the transaction to persist the changes
		frappe.db.commit()
		
		return {
			"success": True,
			"imported_count": imported_count,
			"updated_count": updated_count,
			"skipped_count": skipped_count,
			"errors": errors if errors else None
		}
		
	except Exception as e:
		frappe.log_error(f"Error importing financial data for {security_name}: {str(e)}", "Financial Period Import")
		frappe.db.rollback()
		return {
			"success": False,
			"error": str(e)
		}

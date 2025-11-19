# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class CFFinancialPeriod(Document):
	def validate(self):
		"""Validate and compute derived metrics"""
		self.auto_calculate_missing_fields()
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
	
	def auto_calculate_missing_fields(self):
		"""Auto-calculate missing fields from available data"""
		calculated_fields = []
		
		# Calculate Gross Profit: Revenue - Cost of Revenue
		if not self.gross_profit and self.total_revenue and self.cost_of_revenue:
			self.gross_profit = self.total_revenue - self.cost_of_revenue
			calculated_fields.append("Gross Profit")
		
		# Calculate Cost of Revenue: Revenue - Gross Profit
		if not self.cost_of_revenue and self.total_revenue and self.gross_profit:
			self.cost_of_revenue = self.total_revenue - self.gross_profit
			calculated_fields.append("Cost of Revenue")
		
		# Calculate Operating Income: Gross Profit - Operating Expenses
		if not self.operating_income and self.gross_profit and self.operating_expenses:
			self.operating_income = self.gross_profit - self.operating_expenses
			calculated_fields.append("Operating Income")
		
		# Calculate Operating Income: Revenue - Cost of Revenue - Operating Expenses
		if not self.operating_income and self.total_revenue and self.cost_of_revenue and self.operating_expenses:
			self.operating_income = self.total_revenue - self.cost_of_revenue - self.operating_expenses
			if "Operating Income" not in calculated_fields:
				calculated_fields.append("Operating Income")
		
		# Calculate Free Cash Flow: Operating Cash Flow - Capital Expenditures
		if not self.free_cash_flow and self.operating_cash_flow and self.capital_expenditures:
			self.free_cash_flow = self.operating_cash_flow - abs(self.capital_expenditures)
			calculated_fields.append("Free Cash Flow")
		
		# Store calculated fields for notification
		if calculated_fields:
			# Set a message that can be displayed to the user after save
			self.__calculated_fields_msg = f"Auto-calculated: {', '.join(calculated_fields)}"
			frappe.msgprint(
				msg=f"Auto-calculated: {', '.join(calculated_fields)}",
				title="Fields Calculated",
				indicator="blue"
			)
	
	def compute_margins(self):
		"""Compute margin percentages (stored as percentages, e.g., 68.82 for 68.82%)"""
		if self.total_revenue and self.total_revenue != 0:
			if self.gross_profit:
				self.gross_margin = (self.gross_profit / self.total_revenue) * 100
			if self.operating_income:
				self.operating_margin = (self.operating_income / self.total_revenue) * 100
			if self.net_income:
				self.net_margin = (self.net_income / self.total_revenue) * 100
	
	def compute_ratios(self):
		"""Compute financial ratios (percentages stored as 15 for 15%, ratios as decimals)"""
		# ROE (stored as percentage)
		if self.shareholders_equity and self.shareholders_equity != 0 and self.net_income:
			self.roe = (self.net_income / self.shareholders_equity) * 100
		
		# ROA (stored as percentage)
		if self.total_assets and self.total_assets != 0 and self.net_income:
			self.roa = (self.net_income / self.total_assets) * 100
		
		# Debt to Equity (stored as ratio, not percentage)
		if self.shareholders_equity and self.shareholders_equity != 0 and self.total_debt:
			self.debt_to_equity = self.total_debt / self.shareholders_equity
		
		# Current Ratio (stored as ratio, not percentage)
		if self.current_liabilities and self.current_liabilities != 0 and self.current_assets:
			self.current_ratio = self.current_assets / self.current_liabilities
		
		# Quick Ratio (stored as ratio, not percentage)
		if self.current_liabilities and self.current_liabilities != 0 and self.current_assets:
			inventory = self.inventory or 0
			self.quick_ratio = (self.current_assets - inventory) / self.current_liabilities
		
		# Asset Turnover (stored as ratio, not percentage)
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


@frappe.whitelist()
def bulk_import_financial_periods(security_names, replace_existing=False, respect_override=True, stop_on_error=False, progress_id=None):
	"""Bulk import financial periods for multiple securities with optional realtime progress.

	Args:
		security_names (list|str): List of CF Security names or JSON/CSV string
		replace_existing (bool): Replace ALL existing periods regardless of quality
		respect_override (bool): Skip periods with override_yahoo=1 when updating
		stop_on_error (bool): Abort remaining imports after first error
		progress_id (str): If provided, will publish realtime events on channel 'bulk_import_progress_<progress_id>'

		Returns:
			Dict summary including per-security results and aggregate counts.
		"""
	import json
	
	# Normalize list input
	if isinstance(security_names, str):
		try:
			parsed = frappe.parse_json(security_names)
			if isinstance(parsed, list):
				security_names = parsed
			else:
				security_names = [s.strip() for s in security_names.split(',') if s.strip()]
		except Exception:
			security_names = [s.strip() for s in security_names.split(',') if s.strip()]
	
		results = []
		total_imported = 0
		total_updated = 0
		total_skipped = 0
		total_errors = 0
		aborted = False
	
		channel = None
		if progress_id:
			channel = f"bulk_import_progress_{progress_id}"
			frappe.publish_realtime(channel, {
				'total': len(security_names),
				'current_index': -1,
				'security': None,
				'imported': 0,
				'updated': 0,
				'skipped': 0,
				'errors_count': 0,
				'finished': False
			})
	
		for idx, sec in enumerate(security_names):
			if aborted:
				break
			try:
				res = import_from_yahoo_finance(
					security_name=sec,
					replace_existing=replace_existing,
					respect_override=respect_override
				)
				imported = res.get('imported_count', 0)
				updated = res.get('updated_count', 0)
				skipped = res.get('skipped_count', 0)
				errors_list = res.get('errors') or []
				results.append({
					'security': sec,
					'imported': imported,
					'updated': updated,
					'skipped': skipped,
					'errors': errors_list
				})
				total_imported += imported
				total_updated += updated
				total_skipped += skipped
				total_errors += len(errors_list)
			except Exception as e:
				frappe.log_error(f"Bulk import error for {sec}: {str(e)}", "Bulk Financial Period Import")
				results.append({
					'security': sec,
					'imported': 0,
					'updated': 0,
					'skipped': 0,
					'errors': [str(e)]
				})
				total_errors += 1
				if stop_on_error:
					aborted = True
	
			if channel:
				frappe.publish_realtime(channel, {
					'total': len(security_names),
					'current_index': idx,
					'security': sec,
					'imported': imported if 'imported' in locals() else 0,
					'updated': updated if 'updated' in locals() else 0,
					'skipped': skipped if 'skipped' in locals() else 0,
					'errors_count': len(errors_list) if 'errors_list' in locals() else (1 if aborted else 0),
					'finished': False
				})
	
		# Final event
		if channel:
			frappe.publish_realtime(channel, {
				'total': len(security_names),
				'current_index': len(security_names)-1 if security_names else -1,
				'security': None,
				'imported': total_imported,
				'updated': total_updated,
				'skipped': total_skipped,
				'errors_count': total_errors,
				'finished': True
			})
	
		return {
			'success': True,
			'total_imported': total_imported,
			'total_updated': total_updated,
			'total_skipped': total_skipped,
			'total_errors': total_errors,
			'aborted': aborted,
			'results': results
}


def daily_bulk_import_all_securities():
	"""Scheduled task: import periods for all securities (non-destructive).

	Runs with conservative defaults: replace_existing=False, respect_override=True.
	Skips entirely if any exception arises early or if optional settings flag disables it.
	"""
	try:
		# Optional settings toggle (field may not exist yet)
		try:
			settings = frappe.get_single('CF Settings')
			flag = getattr(settings, 'enable_daily_bulk_import_periods', 1)
			if not flag:
				return
		except Exception:
			# If settings doc or field missing, proceed by default
			pass

		security_names = [d.name for d in frappe.get_all('CF Security', fields=['name'])]
		if not security_names:
			return
		result = bulk_import_financial_periods(
			security_names=security_names,
			replace_existing=False,
			respect_override=True,
			stop_on_error=False,
			progress_id=None
		)
		# Log summary (avoid large payload in log)
		frappe.log_error(
			f"Daily bulk import completed: Imported {result['total_imported']} Updated {result['total_updated']} Skipped {result['total_skipped']} Errors {result['total_errors']}",
			"Daily Financial Period Bulk Import"
		)
	except Exception as e:
		frappe.log_error(f"Daily bulk import failed: {str(e)}", "Daily Financial Period Bulk Import Error")


@frappe.whitelist()
def enqueue_bulk_import_financial_periods(security_names=None, replace_existing=False, respect_override=True, stop_on_error=False):
	"""Enqueue background job for bulk import.

	If security_names is None, import all securities.
	Returns: job name and cache key for polling results.
	"""
	import json, uuid
	if security_names is None:
		security_names = [d.name for d in frappe.get_all('CF Security', fields=['name'])]
	elif isinstance(security_names, str):
		try:
			parsed = frappe.parse_json(security_names)
			if isinstance(parsed, list):
				security_names = parsed
			else:
				security_names = [s.strip() for s in security_names.split(',') if s.strip()]
		except Exception:
			security_names = [s.strip() for s in security_names.split(',') if s.strip()]

	job_id = uuid.uuid4().hex[:12]
	cache_key = f"bulk_import_job_result_{job_id}"

	frappe.enqueue(
		"cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period.run_bulk_import_job",
		queue='long',
		job_name=f"bulk_import_{job_id}",
		security_names=security_names,
		replace_existing=replace_existing,
		respect_override=respect_override,
		stop_on_error=stop_on_error,
		cache_key=cache_key
	)
	return {"job_id": job_id, "cache_key": cache_key}


def run_bulk_import_job(security_names, replace_existing=False, respect_override=True, stop_on_error=False, cache_key=None):
	"""Background job runner writes result to cache for later retrieval."""
	result = bulk_import_financial_periods(
		security_names=security_names,
		replace_existing=replace_existing,
		respect_override=respect_override,
		stop_on_error=stop_on_error,
		progress_id=None
	)
	if cache_key:
		frappe.cache().set_value(cache_key, frappe.as_json(result))
	return result


@frappe.whitelist()
def get_bulk_import_job_result(cache_key):
	"""Retrieve cached bulk import result if available."""
	data = frappe.cache().get_value(cache_key)
	if not data:
		return {"ready": False}
	try:
		return {"ready": True, "result": frappe.parse_json(data)}
	except Exception:
		return {"ready": False, "error": "Malformed cache data"}


@frappe.whitelist()
def format_periods_for_ai(
	security_name, 
	period_type="Annual", 
	num_periods=5, 
	include_growth=True,
	format="markdown",
	fields=None
):
	"""
	Format financial period data for AI consumption
	
	Args:
		security_name: Name of the CF Security
		period_type: "Annual", "Quarterly", or "TTM" (default: "Annual")
		num_periods: Number of periods to retrieve (default: 5)
		include_growth: Include YoY growth metrics (default: True)
		format: Output format - "markdown", "text", "json", or "table" (default: "markdown")
		fields: List of specific field names to include (default: None = all key fields)
	
	Returns:
		Formatted string ready for AI prompt injection
	
	Example:
		format_periods_for_ai("MSFT", period_type="Annual", num_periods=5, format="markdown")
	"""
	
	# Get the security details
	security = frappe.get_doc("CF Security", security_name)
	currency = security.currency or "USD"
	
	# Build filter
	filters = {
		"security": security_name,
		"period_type": period_type
	}
	
	# Define default fields if none specified
	if fields is None:
		fields = [
			"name", "fiscal_year", "fiscal_quarter", "period_end_date",
			"total_revenue", "cost_of_revenue", "gross_profit", 
			"operating_expenses", "operating_income", "net_income",
			"diluted_eps", "basic_eps",
			"total_assets", "current_assets", "cash_and_equivalents",
			"total_liabilities", "current_liabilities", "total_debt",
			"shareholders_equity",
			"operating_cash_flow", "free_cash_flow", "capital_expenditures",
			"gross_margin", "operating_margin", "net_margin",
			"roe", "roa", "current_ratio", "debt_to_equity",
			"revenue_growth_yoy", "net_income_growth_yoy", "eps_growth_yoy"
		]
	
	# Query periods
	periods = frappe.get_all(
		"CF Financial Period",
		filters=filters,
		fields=fields,
		order_by="fiscal_year DESC, fiscal_quarter DESC",
		limit=num_periods
	)
	
	if not periods:
		return f"No {period_type} financial periods found for {security_name}."
	
	# Format based on requested format
	if format == "json":
		import json
		return json.dumps(periods, indent=2, default=str)
	
	elif format == "text":
		return _format_as_text(periods, security_name, period_type, currency, include_growth)
	
	elif format == "table":
		return _format_as_table(periods, security_name, period_type, currency, include_growth)
	
	else:  # markdown (default)
		return _format_as_markdown(periods, security_name, period_type, currency, include_growth)


def _format_as_markdown(periods, security_name, period_type, currency, include_growth):
	"""Format periods as markdown"""
	output = [f"## Financial Data for {security_name} ({period_type})\n"]
	output.append(f"*All monetary values in {currency}*\n")
	
	for period in periods:
		# Period header
		period_label = f"{period.fiscal_year}"
		if period.fiscal_quarter:
			period_label += f" {period.fiscal_quarter}"
		output.append(f"### {period_label}\n")
		
		# Income Statement
		output.append("**Income Statement:**")
		if period.total_revenue:
			output.append(f"- Revenue: {_format_number(period.total_revenue, currency)}")
		if period.gross_profit:
			output.append(f"- Gross Profit: {_format_number(period.gross_profit, currency)}")
		if period.operating_income:
			output.append(f"- Operating Income: {_format_number(period.operating_income, currency)}")
		if period.net_income:
			output.append(f"- Net Income: {_format_number(period.net_income, currency)}")
		if period.diluted_eps:
			output.append(f"- EPS (Diluted): {currency} {period.diluted_eps:.2f}")
		
		# Margins
		if period.gross_margin or period.operating_margin or period.net_margin:
			output.append("\n**Profitability Margins:**")
			if period.gross_margin:
				output.append(f"- Gross Margin: {period.gross_margin*100:.2f}%")
			if period.operating_margin:
				output.append(f"- Operating Margin: {period.operating_margin*100:.2f}%")
			if period.net_margin:
				output.append(f"- Net Margin: {period.net_margin*100:.2f}%")
		
		# Balance Sheet
		if period.total_assets or period.shareholders_equity:
			output.append("\n**Balance Sheet:**")
			if period.total_assets:
				output.append(f"- Total Assets: {_format_number(period.total_assets, currency)}")
			if period.current_assets:
				output.append(f"- Current Assets: {_format_number(period.current_assets, currency)}")
			if period.cash_and_equivalents:
				output.append(f"- Cash: {_format_number(period.cash_and_equivalents, currency)}")
			if period.total_liabilities:
				output.append(f"- Total Liabilities: {_format_number(period.total_liabilities, currency)}")
			if period.total_debt:
				output.append(f"- Total Debt: {_format_number(period.total_debt, currency)}")
			if period.shareholders_equity:
				output.append(f"- Shareholders' Equity: {_format_number(period.shareholders_equity, currency)}")
		
		# Cash Flow
		if period.operating_cash_flow or period.free_cash_flow:
			output.append("\n**Cash Flow:**")
			if period.operating_cash_flow:
				output.append(f"- Operating Cash Flow: {_format_number(period.operating_cash_flow, currency)}")
			if period.free_cash_flow:
				output.append(f"- Free Cash Flow: {_format_number(period.free_cash_flow, currency)}")
			if period.capital_expenditures:
				output.append(f"- CapEx: {_format_number(period.capital_expenditures, currency)}")
		
		# Financial Ratios
		if period.roe or period.roa or period.current_ratio:
			output.append("\n**Key Ratios:**")
			if period.roe:
				output.append(f"- Return on Equity (ROE): {period.roe*100:.2f}%")
			if period.roa:
				output.append(f"- Return on Assets (ROA): {period.roa*100:.2f}%")
			if period.current_ratio:
				output.append(f"- Current Ratio: {period.current_ratio:.2f}")
			if period.debt_to_equity:
				output.append(f"- Debt-to-Equity: {period.debt_to_equity:.2f}")
		
		# YoY Growth
		if include_growth and (period.revenue_growth_yoy or period.net_income_growth_yoy):
			output.append("\n**Year-over-Year Growth:**")
			if period.revenue_growth_yoy:
				growth_sign = "+" if period.revenue_growth_yoy > 0 else ""
				output.append(f"- Revenue Growth: {growth_sign}{period.revenue_growth_yoy*100:.2f}%")
			if period.net_income_growth_yoy:
				growth_sign = "+" if period.net_income_growth_yoy > 0 else ""
				output.append(f"- Net Income Growth: {growth_sign}{period.net_income_growth_yoy*100:.2f}%")
			if period.eps_growth_yoy:
				growth_sign = "+" if period.eps_growth_yoy > 0 else ""
				output.append(f"- EPS Growth: {growth_sign}{period.eps_growth_yoy*100:.2f}%")
		
		output.append("")  # Blank line between periods
	
	return "\n".join(output)


def _format_as_text(periods, security_name, period_type, currency, include_growth):
	"""Format periods as plain text"""
	output = [f"Financial Data for {security_name} ({period_type})"]
	output.append(f"All monetary values in {currency}")
	output.append("=" * 60)
	
	for period in periods:
		period_label = f"{period.fiscal_year}"
		if period.fiscal_quarter:
			period_label += f" {period.fiscal_quarter}"
		
		output.append(f"\n{period_label}")
		output.append("-" * 40)
		
		if period.total_revenue:
			output.append(f"Revenue: {_format_number(period.total_revenue, currency)}")
		if period.net_income:
			output.append(f"Net Income: {_format_number(period.net_income, currency)}")
		if period.diluted_eps:
			output.append(f"EPS: {currency} {period.diluted_eps:.2f}")
		
		if period.gross_margin:
			output.append(f"Gross Margin: {period.gross_margin*100:.1f}%")
		if period.net_margin:
			output.append(f"Net Margin: {period.net_margin*100:.1f}%")
		
		if period.roe:
			output.append(f"ROE: {period.roe*100:.1f}%")
		if period.free_cash_flow:
			output.append(f"Free Cash Flow: {_format_number(period.free_cash_flow, currency)}")
		
		if include_growth and period.revenue_growth_yoy:
			growth_sign = "+" if period.revenue_growth_yoy > 0 else ""
			output.append(f"Revenue Growth YoY: {growth_sign}{period.revenue_growth_yoy*100:.1f}%")
	
	return "\n".join(output)


def _format_as_table(periods, security_name, period_type, currency, include_growth):
	"""Format periods as ASCII table"""
	output = [f"Financial Data for {security_name} ({period_type}) - All values in {currency}\n"]
	
	# Table header
	header = ["Period", "Revenue", "Net Income", "EPS", "Gross Margin", "Net Margin", "ROE"]
	if include_growth:
		header.append("Rev Growth")
	
	# Build rows
	rows = []
	for period in periods:
		period_label = str(period.fiscal_year)
		if period.fiscal_quarter:
			period_label += f" {period.fiscal_quarter}"
		
		row = [
			period_label,
			_format_number(period.total_revenue, currency, short=True) if period.total_revenue else "-",
			_format_number(period.net_income, currency, short=True) if period.net_income else "-",
			f"{period.diluted_eps:.2f}" if period.diluted_eps else "-",
			f"{period.gross_margin*100:.1f}%" if period.gross_margin else "-",
			f"{period.net_margin*100:.1f}%" if period.net_margin else "-",
			f"{period.roe*100:.1f}%" if period.roe else "-"
		]
		
		if include_growth:
			if period.revenue_growth_yoy:
				growth_sign = "+" if period.revenue_growth_yoy > 0 else ""
				row.append(f"{growth_sign}{period.revenue_growth_yoy*100:.1f}%")
			else:
				row.append("-")
		
		rows.append(row)
	
	# Calculate column widths
	col_widths = [max(len(str(row[i])) for row in [header] + rows) for i in range(len(header))]
	
	# Format table
	separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
	
	output.append(separator)
	output.append("| " + " | ".join(header[i].ljust(col_widths[i]) for i in range(len(header))) + " |")
	output.append(separator)
	
	for row in rows:
		output.append("| " + " | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(row))) + " |")
	
	output.append(separator)
	
	return "\n".join(output)


def _format_number(value, currency, short=False):
	"""Format a number with currency symbol and optional abbreviation"""
	if value is None:
		return "N/A"
	
	# Currency symbols
	currency_symbols = {
		'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥',
		'CNY': '¥', 'HKD': 'HK$', 'AUD': 'A$', 'CAD': 'C$'
	}
	symbol = currency_symbols.get(currency, currency + ' ')
	
	if short:
		# Short format with abbreviations
		if abs(value) >= 1e12:
			return f"{symbol}{value/1e12:.2f}T"
		elif abs(value) >= 1e9:
			return f"{symbol}{value/1e9:.2f}B"
		elif abs(value) >= 1e6:
			return f"{symbol}{value/1e6:.2f}M"
		elif abs(value) >= 1e3:
			return f"{symbol}{value/1e3:.2f}K"
		else:
			return f"{symbol}{value:,.2f}"
	else:
		# Full format with commas
		if abs(value) >= 1e9:
			return f"{symbol}{value/1e9:.2f}B"
		elif abs(value) >= 1e6:
			return f"{symbol}{value/1e6:.2f}M"
		else:
			return f"{symbol}{value:,.2f}"


@frappe.whitelist()
def get_previous_period(security, period_type, fiscal_year, fiscal_quarter=None):
	"""Get the previous period for comparison or copying
	
	Args:
		security: Security name
		period_type: "Annual" or "Quarterly"
		fiscal_year: Current fiscal year
		fiscal_quarter: Current fiscal quarter (if Quarterly)
	
	Returns:
		Dict with previous period data or None
	"""
	fiscal_year = int(fiscal_year)
	
	if period_type == "Quarterly" and fiscal_quarter:
		# For quarterly, get previous quarter
		quarter_map = {"Q1": None, "Q2": "Q1", "Q3": "Q2", "Q4": "Q3"}
		prev_quarter = quarter_map.get(fiscal_quarter)
		
		if prev_quarter:
			# Same year, previous quarter
			filters = {
				"security": security,
				"period_type": period_type,
				"fiscal_year": fiscal_year,
				"fiscal_quarter": prev_quarter
			}
		else:
			# Q1, so get Q4 of previous year
			filters = {
				"security": security,
				"period_type": period_type,
				"fiscal_year": fiscal_year - 1,
				"fiscal_quarter": "Q4"
			}
	else:
		# For annual, get previous year
		filters = {
			"security": security,
			"period_type": period_type,
			"fiscal_year": fiscal_year - 1
		}
	
	prev_period = frappe.db.get_value(
		"CF Financial Period",
		filters,
		["*"],
		as_dict=True
	)
	
	return prev_period


@frappe.whitelist()
def test_function(security_name):
	"""Test function to return sample AI prompt"""
	
	# Get the last 4 quarterly periods and 1 annual period
	quarterly_periods = frappe.get_all(
		"CF Financial Period",
		filters={"security": security_name, "period_type": "Quarterly"},
		fields=["fiscal_year", "fiscal_quarter", "total_revenue", "net_income", "diluted_eps"],
		order_by="fiscal_year DESC, fiscal_quarter DESC",
		limit=4
	)
	
	annual_period = frappe.get_all(
		"CF Financial Period",
		filters={"security": security_name, "period_type": "Annual"},
		fields=["fiscal_year", "total_revenue", "net_income", "diluted_eps"],
		order_by="fiscal_year DESC",
		limit=1
	)
	
	# Combine periods
	periods = quarterly_periods + annual_period
	
	if not periods:
		return "No financial data found for this security."
	
	# Format for AI
	formatted_periods = format_periods_for_ai(security_name, period_type="Quarterly", num_periods=4, format="markdown")
	
	# Sample prompt using the formatted data
	prompt = f"""
	You are an expert financial analyst. Based on the following data for the last 4 quarters and 1 annual period for {security_name}, provide a comprehensive analysis including trends, growth metrics, and any red flags.
	
	{formatted_periods}
	
	Please structure your analysis with headings, bullet points, and clear metrics. Highlight any significant changes or concerns.
	"""
	
	return prompt
